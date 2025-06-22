-- SQL schema for Music Forecaster prototype

-- Table of musical eras (milestone-based)
CREATE TABLE era (
    era_id SERIAL PRIMARY KEY,
    label VARCHAR(100) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL
);

-- Artists with principal aspects
CREATE TABLE artist (
    artist_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    country VARCHAR(100),
    is_group BOOLEAN NOT NULL DEFAULT FALSE,      
    age_category VARCHAR(20) NOT NULL CHECK (age_category IN ('teen', 'adult')),
    theory_background BOOLEAN NOT NULL DEFAULT FALSE
);

-- Genre table
CREATE TABLE genre (
    genre_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    parent_genre_id INT REFERENCES genre(genre_id) ON DELETE SET NULL
);

-- Song metadata
CREATE TABLE song (
    song_id UUID PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    artist_id INT NOT NULL REFERENCES artist(artist_id) ON DELETE SET NULL,
    genre_id INT REFERENCES genre(genre_id) ON DELETE SET NULL,
    release_date DATE NOT NULL,
    language VARCHAR(50),
    duration_seconds INT NOT NULL
);

-- Chart performance
CREATE TABLE song_chart (
    chart_id SERIAL PRIMARY KEY,
    song_id UUID NOT NULL REFERENCES song(song_id) ON DELETE CASCADE,
    chart_name VARCHAR(100) NOT NULL,
    chart_date DATE NOT NULL,
    position INT NOT NULL
);

-- Audio features (Spotify/Librosa)
CREATE TABLE audio_features (
    song_id UUID PRIMARY KEY REFERENCES song(song_id) ON DELETE CASCADE,
    tempo FLOAT,
    keynote INT,
    musical_mode INT,
    time_signature INT,
    loudness FLOAT,
    danceability FLOAT,
    energy FLOAT,
    valence FLOAT,
    acousticness FLOAT,
    instrumentalness FLOAT,
    speechiness FLOAT,
    instrument VARCHAR(100)
);

-- Metadata-derived features
CREATE TABLE metadata_features (
    song_id UUID PRIMARY KEY REFERENCES song(song_id) ON DELETE CASCADE,
    has_featured_artists BOOLEAN,
    label_type VARCHAR(20) CHECK (label_type IN ('major', 'indie'))
);

-- Chart-derived aggregates per year & genre
CREATE TABLE chart_derived_features (
    id SERIAL PRIMARY KEY,
    year INT NOT NULL,
    genre_id INT NOT NULL REFERENCES genre(genre_id) ON DELETE CASCADE,
    avg_peak_position FLOAT,
    count_top_100 INT
);

-- Macro & contextual features by year
CREATE TABLE contextual_features (
    year INT PRIMARY KEY,
    gdp_growth FLOAT,
    unemployment_rate FLOAT,
    internet_penetration FLOAT,
    event_count INT,
    tension FLOAT
);

-- Link years to eras
CREATE TABLE era_year (
    era_id INT NOT NULL REFERENCES era(era_id) ON DELETE CASCADE,
    year INT NOT NULL,
    PRIMARY KEY (era_id, year)
);

-- Audience demographics by genre (or artist) and year
CREATE TABLE audience (
    audience_id SERIAL PRIMARY KEY,
    genre_id INT REFERENCES genre(genre_id) ON DELETE SET NULL,
    artist_id INT REFERENCES artist(artist_id) ON DELETE SET NULL,
    year INT NOT NULL,
    avg_age FLOAT,
    pct_male FLOAT,
    pct_female FLOAT,
    avg_openness FLOAT,
    avg_conscientiousness FLOAT,
    avg_extraversion FLOAT,
    avg_agreeableness FLOAT,
    avg_neuroticism FLOAT
);

-- Prediction targets table (for training)
CREATE TABLE training_targets (
    year INT PRIMARY KEY,
    avg_tempo FLOAT,
    avg_danceability FLOAT,
    avg_energy FLOAT,
    avg_valence FLOAT,
    avg_loudness FLOAT,
    avg_duration_seconds FLOAT,
    pct_featured_artists FLOAT,
    pct_major_label FLOAT,
    avg_peak_position_overall FLOAT,
    count_top_hits INT,
    pct_groups FLOAT,
    pct_teens FLOAT,
    pct_with_theory_background FLOAT
);
