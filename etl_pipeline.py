# etl_pipeline.py
"""
ETL pipeline to load music data for 1920–1924 into the Music Forecaster PostgreSQL database.
Sources:
  - Historic charts: Wikipedia scrapes via fetch_charts module
  - Metadata & genre: MusicBrainz Web API
  - Audio features: Librosa analysis on locally stored recordings or fallback dataset
  - Contextual features: manually defined tension values

Prerequisites:
  - .env with DATABASE_URL set
  - fetch_charts.py available in the same folder
"""

from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials

import os
import glob
import logging
import pandas as pd
import librosa

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from musicbrainzngs import set_useragent, search_recordings, get_artist_by_id
from fetch_charts import fetch_top_records

# ——— Logging ———
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("etl_pipeline")

# ——— Configuration ———
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
set_useragent("MusicForecasterETL", "1.0", "youremail@example.com")

# ——— Configuration ——— (below set_useragent)
# Initialize Spotify client
sp = Spotify(auth_manager=SpotifyClientCredentials())

# ——— Helper: upsert DataFrame ———
def upsert_df(conn, df: pd.DataFrame, table: str):
    if df.empty:
        logger.info(f"No rows to insert into `{table}`")
    else:
        df.to_sql(table, conn, if_exists="append", index=False)
        logger.info(f"Inserted {len(df)} rows into `{table}`")

def find_or_create_artist(conn, name: str, mb_artist_id: str):
    """Fetch or insert artist, now storing country too."""
    cache = find_or_create_artist.cache
    if mb_artist_id in cache:
        return cache[mb_artist_id]

    # 1) Fetch country from MusicBrainz
    mb_data = get_artist_by_id(mb_artist_id, includes=['tags'])
    country = mb_data['artist'].get('country')  # e.g. 'US'

    # 2) Check if artist exists
    row = conn.execute(text(
        "SELECT artist_id FROM artist WHERE name=:n"
    ), {'n': name}).first()

    if row:
        aid = row.artist_id
        # Optionally update country if missing
        conn.execute(text(
            "UPDATE artist SET country = coalesce(country,:c) WHERE artist_id=:id"
        ), {'c': country, 'id': aid})
    else:
        # Insert with country
        res = conn.execute(text(
            "INSERT INTO artist(name,country,age_category,is_group,theory_background) "
            "VALUES(:n,:c,'adult',FALSE,FALSE) RETURNING artist_id"
        ), {'n': name, 'c': country})
        aid = res.scalar()

    cache[mb_artist_id] = aid
    return aid

def find_or_create_genre(conn, tag_list):
    """Pick the top tag and insert into genre table if needed."""
    if not tag_list:
        return None
    # Pick the most frequent tag
    top_tag = max(tag_list, key=lambda t: t.get('count',0))['name']
    # Check existence
    row = conn.execute(text(
        "SELECT genre_id FROM genre WHERE name=:g"
    ), {'g': top_tag}).first()
    if row:
        return row.genre_id
    # Insert new genre
    res = conn.execute(text(
        "INSERT INTO genre(name) VALUES(:g) RETURNING genre_id"
    ), {'g': top_tag})
    return res.scalar()
  
find_or_create_artist.cache = {}

# ——— Helper: MusicBrainz lookup ———
def find_musicbrainz(title: str, artist: str):
    res = search_recordings(recording=title, artist=artist, limit=1, dur=None)
    items = res.get("recording-list", [])
    return items[0] if items else None
  
# ——— Helper: Get Spotify Track ID from title + artist ———
def get_spotify_id(track_title: str, artist_name: str) -> str | None:
    """
    Return the Spotify track ID for the given track title and artist name.
    This does a two‐step lookup:
      1) Find the Spotify artist ID for artist_name
      2) Find the Spotify track ID for track_title by that artist
    Caches results in‑process to minimize Spotify API calls.
    """
    cache = get_spotify_id.cache
    key = (track_title.lower(), artist_name.lower())
    if key in cache:
        return cache[key]

    # 1) lookup artist
    artist_res = sp.search(q=f"artist:{artist_name}", type="artist", limit=1)
    items = artist_res.get("artists", {}).get("items", [])
    if not items:
        cache[key] = None
        return None
    spotify_artist_id = items[0]["id"]

    # 2) lookup track
    track_res = sp.search(
        q=f"track:{track_title} artist:{spotify_artist_id}",
        type="track", limit=1
    )
    tracks = track_res.get("tracks", {}).get("items", [])
    spotify_track_id = tracks[0]["id"] if tracks else None

    cache[key] = spotify_track_id
    return spotify_track_id

# initialize cache
get_spotify_id.cache = {}


# ——— Helper: Extract audio features via Spotify ———
def extract_spotify_features(song_ids: list[str]) -> pd.DataFrame:
    """
    Given a list of Spotify track IDs (which match your MB UUIDs only 
    if you have Spotify IDs—otherwise you need to map MB IDs to Spotify),
    fetch the full audio_features in batches of 50.
    """
    features = []
    # Spotify allows up to 100 IDs per call; we'll batch 50
    for i in range(0, len(song_ids), 50):
        batch = song_ids[i:i+50]
        afs = sp.audio_features(batch)
        for a in afs:
            if a is None:
                continue
            features.append({
                "song_id": a["id"],           # Spotify ID, must align with your song_id
                "tempo": a["tempo"],
                "keynote": a["key"],
                "musical_mode": a["mode"],
                "time_signature": a["time_signature"],
                "loudness": a["loudness"],
                "danceability": a["danceability"],
                "energy": a["energy"],
                "valence": a["valence"],
                "acousticness": a["acousticness"],
                "instrumentalness": a["instrumentalness"],
                "speechiness": a["speechiness"],
                # no reliable 'instrument' field via this API
                "instrument": None
            })
    return pd.DataFrame(features)

# ——— In etl_year(), replace the Librosa section with: ———
    # After you build songs (list of dicts) and have all their song_ids:
    song_ids = [row["song_id"] for row in songs]

    # 3a) Fetch Spotify audio features in bulk
    spotify_df = extract_spotify_features(song_ids)
    upsert_df(conn, spotify_df, "audio_features")
  
# ——— Helper: Contextual features ———
def fetch_contextual_year(year: int):
    tension = {1920:0.2, 1921:0.3, 1922:0.3, 1923:0.4, 1924:0.4}.get(year, 0.0)
    return {
        "year": year,
        "gdp_growth": None,
        "unemployment_rate": None,
        "internet_penetration": 0.0,
        "event_count": None,
        "tension": tension
    }

# ——— ETL for one year ———
def etl_year(year: int, conn):
    logger.info(f"Starting ETL for {year}")
    # 1) fetch chart data
    try:
        chart = fetch_top_records(year)
    except Exception as e:
        logger.error(f"Could not fetch chart for {year}: {e}")
        return

    songs, charts, audio, context, spotify_ids = [], [], [], [], []

    # 2) process each record
    for _, row in chart.iterrows():
        title = row["title"]
        artist_name = row["artist"]
        pos = row["position"]

        mb = find_musicbrainz(title, artist_name)
        if not mb:
            logger.warning(f"No MusicBrainz match for {title} by {artist_name}")
            continue
        sid = mb["id"]
 
        aid = find_or_create_artist(conn, artist_name, mb['artist-credit'][0]['artist']['id'])

        tags = mb.get('tag-list', [])
        genre_id = find_or_create_genre(conn, tags)
        
        duration_ms  = 0
        duration_ms  = int(mb.get('dur', 0))  # duration in ms, might be missing
        duration_sec = duration_ms // 1000
        
        # prepare song row
        songs.append({
            "song_id": sid,
            "title": title,
            "artist_id": aid,
            "genre_id": genre_id,
            "release_date": f"{year}-01-01",
            "language": None,
            "duration_seconds": duration_sec
        })
        # prepare chart row
        charts.append({
            "song_id": sid,
            "chart_name": "Billboard",
            "chart_date": f"{year}-01-01",
            "position": pos
        })
    
        spotify_id = get_spotify_id(title, artist_name)

        if not spotify_id:
          logger.warning(f"No Spotify match for {title} by {artist_name}")
        continue

        # collect spotify_ids to batch‐fetch features later
        spotify_ids.append(spotify_id)

    # 3a) Fetch Spotify audio features in bulk
    spotify_df = extract_spotify_features(spotify_ids)
    upsert_df(conn, spotify_df, "audio_features")

    # 3) contextual
    context.append(fetch_contextual_year(year))

    # 4) load into PostgreSQL
    upsert_df(conn, pd.DataFrame(songs), "song")
    upsert_df(conn, pd.DataFrame(charts), "song_chart")
    upsert_df(conn, pd.DataFrame(audio), "audio_features")
    upsert_df(conn, pd.DataFrame(context), "contextual_features")

    logger.info(f"Completed ETL for {year}")

# ——— Main ———
if __name__ == "__main__":
    with engine.begin() as conn:
        for y in range(1920, 2025):
            etl_year(y, conn)
    logger.info("All done.")