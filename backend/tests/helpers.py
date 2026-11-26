"""Shared builders for tests: a small synthetic Letterboxd export and fake TMDB data."""
import io
import zipfile


def make_zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return buffer.getvalue()


# 36 films spread over three decades so decade/genre thresholds (>=5) are met.
FILMS = []
for i in range(12):
    FILMS.append((f"Seventies Film {i}", 1970 + (i % 9)))
    FILMS.append((f"Nineties Film {i}", 1990 + (i % 9)))
    FILMS.append((f"Recent Film {i}", 2010 + (i % 9)))


def letterboxd_export() -> bytes:
    diary = ["Date,Name,Year,Letterboxd URI,Rating,Rewatch,Tags,Watched Date"]
    ratings = ["Date,Name,Year,Letterboxd URI,Rating"]
    watched = ["Date,Name,Year,Letterboxd URI"]
    for index, (name, year) in enumerate(FILMS):
        day = 1 + (index % 28)
        month = 1 + (index // 28)
        date = f"2024-{month:02d}-{day:02d}"
        rating = [4.0, 3.5, 5.0, 2.5, 3.0][index % 5]
        rewatch = "Yes" if index % 9 == 0 else ""
        diary.append(f"{date},{name},{year},https://boxd.it/{index},{rating},{rewatch},,{date}")
        ratings.append(f"{date},{name},{year},https://boxd.it/{index},{rating}")
        watched.append(f"{date},{name},{year},https://boxd.it/{index}")
    return make_zip([
        ("diary.csv", "\n".join(diary) + "\n"),
        ("ratings.csv", "\n".join(ratings) + "\n"),
        ("watched.csv", "\n".join(watched) + "\n"),
        # Real list exports start with a metadata preamble that breaks naive CSV parsing.
        ("lists/favourites.csv",
         "Letterboxd list export v7\nDate,Name,Tags,URL,Description\n2024-01-01,Favs,,https://x,desc\n\n"
         "Position,Name,Year,URL,Description\n1,Seventies Film 0,1970,https://x,\n"),
    ])


def fake_tmdb(title: str, year):
    n = abs(hash(title)) % 7
    return {
        "tmdb_id": abs(hash(title)) % 100000,
        "title": title,
        "year": year,
        "search_key": title.lower(),
        "genres": [{"id": 18, "name": "Drama"}, {"id": 35 + n, "name": ["Comedy", "Thriller", "Romance", "Horror", "Action", "Crime", "Mystery"][n]}],
        "directors": [{"id": n, "name": f"Director {n}", "profile_path": "/d.jpg"}],
        "cast_members": [{"id": 100 + n, "name": f"Actor {n}", "character": "X", "order": 0, "profile_path": "/a.jpg"}],
        "runtime": 90 + n * 5,
        "production_countries": [{"iso": "US", "name": "United States of America"}],
        "original_language": "en",
        "spoken_languages": [{"iso": "en", "name": "English"}],
        "release_date": f"{year}-06-01",
        "poster_path": "/poster.jpg",
        "vote_average": 6.0 + n * 0.4,
        "popularity": 10.0,
    }


class FakeTMDBService:
    """Stands in for TMDBService: no network, deterministic data, real callback flow."""

    async def enrich_batch(self, movies, progress_callback=None):
        results = []
        for i, movie in enumerate(movies, start=1):
            results.append({**movie, "tmdb": fake_tmdb(movie["title"], movie.get("year"))})
            if progress_callback:
                await progress_callback(i, len(movies))
        return results

    async def enrich_favorite_films(self, favorite_urls):
        return []

    async def close(self):
        return None
