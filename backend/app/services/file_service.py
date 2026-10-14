"""
File service — extract Letterboxd ZIP and parse CSV files.
"""
import zipfile
import os
import io
import pandas as pd
import re
from datetime import datetime


UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def extract_zip(file_bytes: bytes) -> str:
    """Extract a Letterboxd ZIP to a timestamped folder. Returns extraction path."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    extract_path = os.path.join(UPLOAD_DIR, f"export_{timestamp}")
    os.makedirs(extract_path, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        # SEC-01: Validate all paths before extraction to prevent Zip Slip attacks
        abs_extract = os.path.abspath(extract_path)
        for member in zf.infolist():
            target_path = os.path.abspath(os.path.join(extract_path, member.filename))
            if not (target_path.startswith(abs_extract + os.sep) or target_path == abs_extract):
                raise ValueError(
                    "🛑 Security alert: This ZIP archive contains unsafe file paths "
                    "and cannot be processed."
                )
        zf.extractall(extract_path)

    return extract_path


def _find_csv(extract_path: str, name: str) -> str | None:
    """Find a CSV file by name in the extracted directory (supports nested folders)."""
    for root, dirs, files in os.walk(extract_path):
        for f in files:
            if f.lower() == name.lower():
                return os.path.join(root, f)
    return None


# Core CSV files that a valid Letterboxd export must contain (at least one).
_REQUIRED_CSVS = ["diary.csv", "watched.csv", "ratings.csv"]

# Column names that Letterboxd CSVs are expected to have (lowercased).
_EXPECTED_COLUMNS = {"name", "title", "year", "date", "rating", "watched_date"}


def validate_letterboxd_export(extract_path: str) -> None:
    """
    Validate that the extracted ZIP looks like a genuine Letterboxd export.

    Raises ValueError with a user-facing message if:
    - None of the core CSV files (diary/watched/ratings) exist.
    - All found CSVs are empty (zero data rows).
    - CSVs don't contain any expected Letterboxd column names.
    """
    error_message = (
        "🎞️ Looks like we got the wrong reel.\n\n"
        "This doesn't appear to be a valid Letterboxd export. "
        "Upload the original ZIP from Letterboxd and we'll start rolling."
    )

    # 1. Check if at least one core CSV file exists
    found_csvs = {}
    for name in _REQUIRED_CSVS:
        path = _find_csv(extract_path, name)
        if path:
            found_csvs[name] = path

    if not found_csvs:
        raise ValueError(error_message)

    # 2. Check that at least one CSV has data rows and expected columns
    has_movie_data = False
    for name, path in found_csvs.items():
        try:
            df = pd.read_csv(path, nrows=5)  # peek at first 5 rows only
            if df.empty:
                continue
            # Normalize columns for comparison
            cols = {c.strip().lower().replace(' ', '_') for c in df.columns}
            if cols & _EXPECTED_COLUMNS:
                has_movie_data = True
                break
        except Exception:
            continue

    if not has_movie_data:
        raise ValueError(error_message)


def parse_diary(extract_path: str) -> pd.DataFrame:
    """Parse diary.csv from Letterboxd export."""
    path = _find_csv(extract_path, "diary.csv")
    if not path:
        return pd.DataFrame()

    df = pd.read_csv(path)
    # Normalize column names
    df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

    # Parse dates
    if 'watched_date' in df.columns:
        df['watched_date'] = pd.to_datetime(df['watched_date'], errors='coerce')
    elif 'date' in df.columns:
        df['watched_date'] = pd.to_datetime(df['date'], errors='coerce')

    # Parse rating
    if 'rating' in df.columns:
        df['rating'] = pd.to_numeric(df['rating'], errors='coerce')

    # Parse year
    if 'year' in df.columns:
        df['year'] = pd.to_numeric(df['year'], errors='coerce').astype('Int64')

    # Rewatch flag
    if 'rewatch' in df.columns:
        df['is_rewatch'] = df['rewatch'].apply(
            lambda x: True if str(x).strip().lower() in ['yes', 'true', '1'] else False
        )
    else:
        df['is_rewatch'] = False

    return df


def parse_ratings(extract_path: str) -> pd.DataFrame:
    """Parse ratings.csv from Letterboxd export."""
    path = _find_csv(extract_path, "ratings.csv")
    if not path:
        return pd.DataFrame()

    df = pd.read_csv(path)
    df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

    if 'rating' in df.columns:
        df['rating'] = pd.to_numeric(df['rating'], errors='coerce')
    if 'date' in df.columns:
        df['date_rated'] = pd.to_datetime(df['date'], errors='coerce')
    if 'year' in df.columns:
        df['year'] = pd.to_numeric(df['year'], errors='coerce').astype('Int64')

    return df


def parse_watched(extract_path: str) -> pd.DataFrame:
    """Parse watched.csv from Letterboxd export."""
    path = _find_csv(extract_path, "watched.csv")
    if not path:
        return pd.DataFrame()

    df = pd.read_csv(path)
    df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

    if 'date' in df.columns:
        df['watched_date'] = pd.to_datetime(df['date'], errors='coerce')
    if 'year' in df.columns:
        df['year'] = pd.to_numeric(df['year'], errors='coerce').astype('Int64')

    return df


def parse_watchlist(extract_path: str) -> pd.DataFrame:
    """Parse watchlist.csv from Letterboxd export."""
    path = _find_csv(extract_path, "watchlist.csv")
    if not path:
        return pd.DataFrame()

    df = pd.read_csv(path)
    df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

    if 'year' in df.columns:
        df['year'] = pd.to_numeric(df['year'], errors='coerce').astype('Int64')

    return df


def parse_lists(extract_path: str) -> list[dict]:
    """Parse all list CSV files from Letterboxd export."""
    lists_dir = os.path.join(extract_path, "lists")
    if not os.path.isdir(lists_dir):
        return []

    all_lists = []
    for fname in os.listdir(lists_dir):
        if fname.endswith('.csv'):
            list_path = os.path.join(lists_dir, fname)
            df = pd.read_csv(list_path)
            df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]
            list_name = fname.replace('.csv', '').replace('-', ' ').replace('_', ' ').title()
            all_lists.append({
                "name": list_name,
                "count": len(df),
                "films": df.to_dict(orient='records')
            })

    return all_lists


def get_unique_movies(diary_df: pd.DataFrame, watched_df: pd.DataFrame,
                      ratings_df: pd.DataFrame) -> list[dict]:
    """Extract unique movies (title + year) across all CSVs for TMDB enrichment."""
    movies = set()

    for df in [diary_df, watched_df, ratings_df]:
        if df.empty:
            continue
        name_col = 'name' if 'name' in df.columns else 'title' if 'title' in df.columns else None
        if not name_col:
            continue
        for _, row in df.iterrows():
            title = str(row.get(name_col, '')).strip()
            year = row.get('year')
            if title and title != 'nan':
                year_val = int(year) if pd.notna(year) else None
                movies.add((title, year_val))

    return [{"title": t, "year": y} for t, y in sorted(movies)]
