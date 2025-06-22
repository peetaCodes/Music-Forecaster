# fetch_charts.py\n
"""
Module to fetch top popular recordings for a given year (1920–present)
Sources: Wikipedia "<year> in music" pages under various chart header sections

Functions:\n - fetch_top_records(year) -> pd.DataFrame\n Returns DataFrame with columns ['title','artist','position','year']

Usage:\n from fetch_charts import fetch_top_records
 df = fetch_top_records(1920)"""
import requests
import pandas as pd
from bs4 import BeautifulSoup, NavigableString
import re

# List of header patterns for different eras
HEADER_PATTERNS = [
  re.compile(r"Top\s+Popular\s+Recordings\s+\d{4}",re.IGNORECASE),
  re.compile(r"Biggest\s+Hit\s+Singles", re.IGNORECASE),
  re.compile(r"Year[-\s]?End\s+Hot\s+100\s+Singles", re.IGNORECASE),
]


def find_chart_section(soup):
  """Locate the heading tag matching any known chart section pattern."""
  for tag in soup.find_all(['h2', 'h3', 'h4']):
    # remove edit links text
    text = tag.get_text("", strip=True).replace('edit', '').strip()
    for pat in HEADER_PATTERNS:
      if pat.search(text):
        return tag
      return None
    
    
def fetch_top_records(year: int) -> pd.DataFrame:
  """Scrape Wikipedia for top chart recordings for a given year."""
  url = f"https://en.wikipedia.org/wiki/{year}_in_music"
  resp = requests.get(url)
  resp.raise_for_status()
  soup = BeautifulSoup(resp.text, 'html.parser')
  heading = find_chart_section(soup)
  if not heading:
    raise ValueError(f"Could not find a chart section header for year {year} on page {url}.")
    
  # Navigate to container under heading
  # The heading and its edit link are wrapped in a div; move to parent
  container = heading.parent
  records = []
  
  for elem in container.next_siblings:
    if isinstance(elem, NavigableString):
      continue
      # Stop when next section header appears
      if elem.name == 'div' and 'mw-heading' in elem.get('class', []):
        break
        
      # Table format
      if elem.name == 'table':
        rows = elem.find_all('tr')[1:]
        for row in rows:
          cells = row.find_all(['th', 'td'])
          if len(cells) >= 3:
            try:
              pos = int(cells[0].get_text(strip=True))
            except ValueError:
              continue
              artist = cells[1].get_text(strip=True)
            
          title = cells[2].get_text(strip=True).strip('"')
          records.append({'title': title, 'artist': artist, 'position': pos})
          break
        
      # List format
      if elem.name in ['ul', 'ol']:
        for li in elem.find_all('li'):
          text = li.get_text(separator='|', strip=True)
          parts = text.split('|')