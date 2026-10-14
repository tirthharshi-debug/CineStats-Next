"""
Stats service — computes all analytics from diary/ratings/watched data + TMDB enrichment.
Returns structured dicts ready for JSON serialization.

Key approach: use ratings.csv as the canonical source for per-film ratings (one row per film),
and diary.csv as the canonical source for watching activity (dates, rewatches). This avoids
double-counting films that appear in both.
"""
import pandas as pd
import numpy as np
from collections import Counter, defaultdict
from datetime import datetime, timedelta


def compute_basic_stats(diary_df: pd.DataFrame, ratings_df: pd.DataFrame,
                        watched_df: pd.DataFrame) -> dict:
    """BASIC (Free-tier) statistics."""
    # Total unique films — use watched.csv (canonical), fallback to diary
    source = watched_df if not watched_df.empty else diary_df
    name_col = 'name' if 'name' in source.columns else 'title'
    total_films = source[name_col].nunique() if not source.empty else 0

    # Diary stats
    total_diary_entries = len(diary_df) if not diary_df.empty else 0
    total_rewatches = int(diary_df['is_rewatch'].sum()) if (not diary_df.empty and 'is_rewatch' in diary_df.columns) else 0

    # Ratings — use ratings.csv as canonical (one rating per film)
    all_ratings = pd.Series(dtype=float)
    if not ratings_df.empty and 'rating' in ratings_df.columns:
        all_ratings = ratings_df['rating'].dropna()
    elif not diary_df.empty and 'rating' in diary_df.columns:
        # Fallback: unique ratings from diary (latest per film)
        name_col_d = 'name' if 'name' in diary_df.columns else 'title'
        all_ratings = diary_df.dropna(subset=['rating']).drop_duplicates(
            subset=[name_col_d], keep='last'
        )['rating']

    avg_rating = round(float(all_ratings.mean()), 2) if not all_ratings.empty else 0

    # Rating distribution (0.5 to 5.0 in 0.5 steps)
    rating_dist = {}
    if not all_ratings.empty:
        for r in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]:
            rating_dist[str(r)] = int((all_ratings == r).sum())

    # Films per year (watched year from diary)
    films_per_year = {}
    most_active_year = None
    most_active_month = None
    if not diary_df.empty and 'watched_date' in diary_df.columns:
        valid_dates = diary_df.dropna(subset=['watched_date'])
        if not valid_dates.empty:
            year_counts = valid_dates['watched_date'].dt.year.value_counts().sort_index()
            films_per_year = {str(int(k)): int(v) for k, v in year_counts.items()}
            most_active_year = int(year_counts.idxmax())

            month_counts = valid_dates['watched_date'].dt.month.value_counts()
            month_names = {1: 'January', 2: 'February', 3: 'March', 4: 'April',
                           5: 'May', 6: 'June', 7: 'July', 8: 'August',
                           9: 'September', 10: 'October', 11: 'November', 12: 'December'}
            most_active_month = month_names.get(int(month_counts.idxmax()), 'Unknown')

    # First and most recent watched
    first_watched = None
    most_recent_watched = None
    if not diary_df.empty and 'watched_date' in diary_df.columns:
        valid = diary_df.dropna(subset=['watched_date']).sort_values('watched_date')
        if not valid.empty:
            nc = 'name' if 'name' in valid.columns else 'title'
            first_row = valid.iloc[0]
            last_row = valid.iloc[-1]
            first_watched = {
                "title": str(first_row.get(nc, '')),
                "date": str(first_row['watched_date'].date())
            }
            most_recent_watched = {
                "title": str(last_row.get(nc, '')),
                "date": str(last_row['watched_date'].date())
            }

    return {
        "total_films": total_films,
        "total_diary_entries": total_diary_entries,
        "total_rewatches": total_rewatches,
        "average_rating": avg_rating,
        "rating_distribution": rating_dist,
        "films_per_year": films_per_year,
        "most_active_year": most_active_year,
        "most_active_month": most_active_month,
        "first_watched": first_watched,
        "most_recent_watched": most_recent_watched,
    }


def compute_pro_stats(diary_df: pd.DataFrame, ratings_df: pd.DataFrame) -> dict:
    """PRO-level statistics."""
    results = {}

    # Films per decade (release year) — use diary as source, deduplicate by film name
    decade_dist = {}
    decade_ratings = defaultdict(list)
    if not diary_df.empty and 'year' in diary_df.columns:
        name_col = 'name' if 'name' in diary_df.columns else 'title'
        unique_films = diary_df.dropna(subset=['year']).drop_duplicates(subset=[name_col])
        decades = (unique_films['year'] // 10 * 10).astype(int)
        for d, count in decades.value_counts().sort_index().items():
            decade_dist[f"{d}s"] = int(count)
        # Collect ratings per decade for avg
        if 'rating' in unique_films.columns:
            for _, row in unique_films.iterrows():
                r = row.get('rating')
                if pd.notna(r) and pd.notna(row['year']):
                    dec = int(row['year'] // 10 * 10)
                    decade_ratings[dec].append(float(r))
    results["films_per_decade"] = decade_dist

    # Watch streaks
    longest_streak = 0
    current_streak = 0
    if not diary_df.empty and 'watched_date' in diary_df.columns:
        dates = diary_df.dropna(subset=['watched_date'])['watched_date'].dt.date.unique()
        dates = sorted(dates)
        if dates:
            streak = 1
            max_streak = 1
            for i in range(1, len(dates)):
                if (dates[i] - dates[i - 1]).days == 1:
                    streak += 1
                    max_streak = max(max_streak, streak)
                else:
                    streak = 1
            longest_streak = max_streak

            # Current streak from today
            today = datetime.now().date()
            cur = 0
            for d in reversed(dates):
                expected = today - timedelta(days=cur)
                if d == expected:
                    cur += 1
                else:
                    break
            current_streak = cur

    results["longest_watch_streak"] = longest_streak
    results["current_watch_streak"] = current_streak

    # Most watched year of release — deduplicate
    if not diary_df.empty and 'year' in diary_df.columns:
        name_col = 'name' if 'name' in diary_df.columns else 'title'
        unique = diary_df.dropna(subset=['year']).drop_duplicates(subset=[name_col])
        if not unique.empty:
            results["most_watched_release_year"] = int(unique['year'].value_counts().idxmax())
        else:
            results["most_watched_release_year"] = None
    else:
        results["most_watched_release_year"] = None

    # Rating trend over time (from diary — includes dates)
    rating_trend = {}
    if not diary_df.empty and 'watched_date' in diary_df.columns and 'rating' in diary_df.columns:
        valid = diary_df.dropna(subset=['watched_date', 'rating']).copy()
        if not valid.empty:
            valid['month_key'] = valid['watched_date'].dt.to_period('M').astype(str)
            monthly_avg = valid.groupby('month_key')['rating'].mean()
            rating_trend = {k: round(float(v), 2) for k, v in monthly_avg.items()}
    results["rating_trend_over_time"] = rating_trend

    # Average rating per year (watching year)
    avg_rating_per_year = {}
    if not diary_df.empty and 'watched_date' in diary_df.columns and 'rating' in diary_df.columns:
        valid = diary_df.dropna(subset=['watched_date', 'rating']).copy()
        if not valid.empty:
            valid['watch_year'] = valid['watched_date'].dt.year
            yearly = valid.groupby('watch_year')['rating'].agg(['mean', 'count'])
            for yr, row in yearly.iterrows():
                avg_rating_per_year[str(int(yr))] = {
                    "average": round(float(row['mean']), 2),
                    "count": int(row['count'])
                }
    results["average_rating_per_year"] = avg_rating_per_year

    # Highest / lowest rated year (min 5 films)
    if avg_rating_per_year:
        qualified = {k: v for k, v in avg_rating_per_year.items() if v["count"] >= 5}
        if qualified:
            results["highest_rated_year"] = max(qualified.items(), key=lambda x: x[1]["average"])
            results["lowest_rated_year"] = min(qualified.items(), key=lambda x: x[1]["average"])
        else:
            results["highest_rated_year"] = None
            results["lowest_rated_year"] = None
    else:
        results["highest_rated_year"] = None
        results["lowest_rated_year"] = None

    # Expose raw decade_ratings for decade_leaderboard (internal use, stripped before response)
    results["_decade_ratings"] = {int(k): v for k, v in decade_ratings.items()}

    return results


def _build_tmdb_lookup(enriched_movies: list[dict]) -> dict:
    """Build a lookup dict from (title_lower, year) -> TMDB data."""
    lookup = {}
    for m in enriched_movies:
        if m.get("tmdb"):
            key = (m["title"].lower().strip(), m.get("year"))
            lookup[key] = m["tmdb"]
    return lookup


def _get_tmdb_for_row(row, lookup: dict):
    """Get TMDB data for a DataFrame row."""
    name_col = 'name' if 'name' in row.index else 'title'
    title = str(row.get(name_col, '')).strip().lower()
    year = row.get('year')
    year_val = int(year) if pd.notna(year) else None
    return lookup.get((title, year_val))


def compute_patron_stats(enriched_movies: list[dict], diary_df: pd.DataFrame,
                         ratings_df: pd.DataFrame) -> dict:
    """PATRON-level statistics (TMDB-powered)."""
    results = {}
    tmdb_lookup = _build_tmdb_lookup(enriched_movies)

    # Use ratings.csv as the canonical per-film source (avoids diary duplication)
    primary_df = ratings_df if not ratings_df.empty else diary_df

    # ─── Genre Analytics ───
    genre_counter = Counter()
    genre_ratings = defaultdict(list)

    if not primary_df.empty:
        name_col = 'name' if 'name' in primary_df.columns else 'title'
        # Deduplicate by film name
        unique_films = primary_df.drop_duplicates(subset=[name_col])
        for _, row in unique_films.iterrows():
            tmdb = _get_tmdb_for_row(row, tmdb_lookup)
            if not tmdb:
                continue
            genres = tmdb.get("genres", [])
            rating = row.get('rating')
            for g in genres:
                gname = g["name"] if isinstance(g, dict) else str(g)
                genre_counter[gname] += 1
                if pd.notna(rating):
                    genre_ratings[gname].append(float(rating))

    most_watched_genre = genre_counter.most_common(1)[0][0] if genre_counter else None
    genre_distribution = dict(genre_counter.most_common(20))
    avg_rating_per_genre = {
        g: round(sum(r) / len(r), 2) for g, r in genre_ratings.items() if r
    }
    favorite_genre = None
    qualified_genres = {g: avg for g, avg in avg_rating_per_genre.items()
                       if len(genre_ratings[g]) >= 5}
    if qualified_genres:
        favorite_genre = max(qualified_genres.items(), key=lambda x: x[1])

    results["genre_analytics"] = {
        "most_watched_genre": most_watched_genre,
        "genre_distribution": genre_distribution,
        "average_rating_per_genre": avg_rating_per_genre,
        "favorite_genre": {"name": favorite_genre[0], "avg_rating": favorite_genre[1]} if favorite_genre else None,
    }

    # ─── Director Analytics ───
    director_counter = Counter()
    director_ratings = defaultdict(list)
    director_profiles = {}  # name -> {profile_path}

    if not primary_df.empty:
        name_col = 'name' if 'name' in primary_df.columns else 'title'
        unique_films = primary_df.drop_duplicates(subset=[name_col])
        for _, row in unique_films.iterrows():
            tmdb = _get_tmdb_for_row(row, tmdb_lookup)
            if not tmdb:
                continue
            directors = tmdb.get("directors", [])
            rating = row.get('rating')
            for d in directors:
                dname = d["name"] if isinstance(d, dict) else str(d)
                director_counter[dname] += 1
                if pd.notna(rating):
                    director_ratings[dname].append(float(rating))
                # Store profile_path for director photo
                if isinstance(d, dict) and d.get("profile_path") and dname not in director_profiles:
                    director_profiles[dname] = {"profile_path": d["profile_path"]}

            # Fallback: extract profile_path from raw_details if not in directors list
            if tmdb.get("raw_details"):
                raw = tmdb["raw_details"]
                if isinstance(raw, str):
                    import json as _json
                    try:
                        raw = _json.loads(raw)
                    except Exception:
                        raw = {}
                crew = raw.get("credits", {}).get("crew", []) if isinstance(raw, dict) else []
                for c in crew:
                    if c.get("job") == "Director" and c.get("profile_path"):
                        cname = c.get("name", "")
                        if cname and cname not in director_profiles:
                            director_profiles[cname] = {"profile_path": c["profile_path"]}

    # Overall avg from all rated films
    all_dir_ratings = [r for rs in director_ratings.values() for r in rs]
    overall_avg = sum(all_dir_ratings) / len(all_dir_ratings) if all_dir_ratings else 0

    most_watched_director = director_counter.most_common(1)[0][0] if director_counter else None
    director_frequency = dict(director_counter.most_common(20))
    highest_rated_director = None
    qualified_dirs = {d: round(sum(r) / len(r), 2)
                      for d, r in director_ratings.items() if len(r) >= 3}
    if qualified_dirs:
        highest_rated_director = max(qualified_dirs.items(), key=lambda x: x[1])

    director_vs_avg = {}
    for d, avg in qualified_dirs.items():
        director_vs_avg[d] = {"avg": avg, "diff": round(avg - overall_avg, 2)}

    results["director_analytics"] = {
        "most_watched_director": most_watched_director,
        "director_frequency": director_frequency,
        "highest_rated_director": {"name": highest_rated_director[0], "avg_rating": highest_rated_director[1]} if highest_rated_director else None,
        "director_vs_average": dict(sorted(director_vs_avg.items(), key=lambda x: x[1]["diff"], reverse=True)[:15]),
        "your_overall_average": round(overall_avg, 2),
        "director_profiles": director_profiles,
    }

    # ─── Actor Analytics ───
    actor_counter = Counter()
    actor_profiles = {}  # name -> profile_path
    for m in enriched_movies:
        tmdb = m.get("tmdb")
        if not tmdb:
            continue
        cast = tmdb.get("cast_members", [])
        for c in cast[:10]:
            cname = c["name"] if isinstance(c, dict) else str(c)
            actor_counter[cname] += 1
            # Store profile_path for actor photo
            if isinstance(c, dict) and c.get("profile_path") and cname not in actor_profiles:
                actor_profiles[cname] = c["profile_path"]

    most_watched_actor = actor_counter.most_common(1)[0][0] if actor_counter else None
    top_10_actors = [
        {"name": n, "count": c, "profile_path": actor_profiles.get(n)}
        for n, c in actor_counter.most_common(10)
    ]
    actor_distribution = dict(actor_counter.most_common(20))

    results["actor_analytics"] = {
        "most_watched_actor": most_watched_actor,
        "top_10_actors": top_10_actors,
        "actor_frequency_distribution": actor_distribution,
    }

    # ─── Runtime Analytics ───
    runtimes = []
    longest_film = None
    shortest_film = None
    for m in enriched_movies:
        tmdb = m.get("tmdb")
        if not tmdb or not tmdb.get("runtime"):
            continue
        rt = tmdb["runtime"]
        if not isinstance(rt, (int, float)) or rt <= 0:
            continue
        runtimes.append(rt)
        if not longest_film or rt > longest_film["runtime"]:
            longest_film = {"title": tmdb.get("title", m.get("title")), "runtime": rt}
        if not shortest_film or rt < shortest_film["runtime"]:
            shortest_film = {"title": tmdb.get("title", m.get("title")), "runtime": rt}

    total_minutes = sum(runtimes)
    results["runtime_analytics"] = {
        "total_runtime_minutes": total_minutes,
        "total_runtime_hours": round(total_minutes / 60, 1),
        "total_runtime_days": round(total_minutes / 1440, 1),
        "average_runtime": round(total_minutes / len(runtimes), 1) if runtimes else 0,
        "longest_film": longest_film,
        "shortest_film": shortest_film,
    }

    # ─── Country Analytics ───
    country_counter = Counter()
    for m in enriched_movies:
        tmdb = m.get("tmdb")
        if not tmdb:
            continue
        countries = tmdb.get("production_countries", [])
        for c in countries:
            cname = c["name"] if isinstance(c, dict) else str(c)
            country_counter[cname] += 1

    results["country_analytics"] = {
        "most_watched_country": country_counter.most_common(1)[0][0] if country_counter else None,
        "country_distribution": dict(country_counter.most_common(20)),
    }

    # ─── Language Analytics ───
    lang_counter = Counter()
    for m in enriched_movies:
        tmdb = m.get("tmdb")
        if not tmdb:
            continue
        langs = tmdb.get("spoken_languages", [])
        for lang in langs:
            if isinstance(lang, dict):
                lname = lang.get("name", lang.get("iso", "Unknown"))
            else:
                lname = str(lang)
            lang_counter[lname] += 1

    results["language_analytics"] = {
        "most_watched_language": lang_counter.most_common(1)[0][0] if lang_counter else None,
        "language_distribution": dict(lang_counter.most_common(20)),
    }

    return results


def compute_advanced_stats(enriched_movies: list[dict], diary_df: pd.DataFrame,
                           ratings_df: pd.DataFrame) -> dict:
    """ADVANCED insight features (beyond Patron)."""
    results = {}
    tmdb_lookup = _build_tmdb_lookup(enriched_movies)

    # Use ratings.csv as canonical source
    primary_df = ratings_df if not ratings_df.empty else diary_df

    # ─── Taste Profile ───
    genre_counter = Counter()
    all_ratings_list = []

    if not primary_df.empty:
        name_col = 'name' if 'name' in primary_df.columns else 'title'
        unique_films = primary_df.drop_duplicates(subset=[name_col])
        for _, row in unique_films.iterrows():
            tmdb = _get_tmdb_for_row(row, tmdb_lookup)
            rating = row.get('rating')
            if pd.notna(rating):
                all_ratings_list.append(float(rating))
            if tmdb:
                for g in tmdb.get("genres", []):
                    gname = g["name"] if isinstance(g, dict) else str(g)
                    genre_counter[gname] += 1

    top_genres = genre_counter.most_common(3)
    avg_r = round(sum(all_ratings_list) / len(all_ratings_list), 2) if all_ratings_list else 0

    taste_labels = []
    if top_genres:
        taste_labels.append(f"Genre affinity: {', '.join(g[0] for g in top_genres)}")
    if avg_r >= 4.0:
        taste_labels.append("Rating style: Generous critic")
    elif avg_r >= 3.0:
        taste_labels.append("Rating style: Balanced viewer")
    elif avg_r >= 2.0:
        taste_labels.append("Rating style: Selective critic")
    else:
        taste_labels.append("Rating style: Tough critic")

    results["taste_profile"] = taste_labels

    # ─── Release Year Stats ───
    # Collect (release_date, year, title) for proper chronological ordering
    film_entries = []
    for m in enriched_movies:
        tmdb = m.get("tmdb")
        if not tmdb:
            continue
        yr = tmdb.get("year")
        if yr is None:
            continue
        yr = int(yr)
        release_date = tmdb.get("release_date", str(yr))
        title = tmdb.get("title", m.get("title", "Unknown"))
        film_entries.append({"release_date": release_date, "year": yr, "title": title})

    if film_entries:
        release_years = [f["year"] for f in film_entries]
        results["average_release_year"] = round(sum(release_years) / len(release_years))

        # Sort by release_date string (YYYY-MM-DD sorts chronologically)
        sorted_by_date = sorted(film_entries, key=lambda f: f["release_date"] or "0000")
        oldest = sorted_by_date[0]
        newest = sorted_by_date[-1]
        results["oldest_film"] = {"title": oldest["title"], "year": oldest["year"]}
        results["newest_film"] = {"title": newest["title"], "year": newest["year"]}
    else:
        results["average_release_year"] = None
        results["oldest_film"] = None
        results["newest_film"] = None

    # ─── Most Rewatched Film ───
    if not diary_df.empty and 'is_rewatch' in diary_df.columns:
        name_col = 'name' if 'name' in diary_df.columns else 'title'
        rewatches = diary_df[diary_df['is_rewatch'] == True]
        if not rewatches.empty:
            most_rw = rewatches[name_col].value_counts()
            results["most_rewatched_film"] = {
                "title": str(most_rw.index[0]),
                "rewatch_count": int(most_rw.iloc[0])
            }
        else:
            results["most_rewatched_film"] = None
    else:
        results["most_rewatched_film"] = None

    # ─── Most Common Genre Combination ───
    genre_combos = Counter()
    for m in enriched_movies:
        tmdb = m.get("tmdb")
        if tmdb:
            raw_genres = tmdb.get("genres", [])
            genres = sorted([g["name"] if isinstance(g, dict) else str(g) for g in raw_genres])
            if len(genres) >= 2:
                combo = " + ".join(genres[:3])
                genre_combos[combo] += 1

    results["most_common_genre_combo"] = genre_combos.most_common(5) if genre_combos else []

    # ─── Release Year vs Rating Correlation ───
    year_rating_pairs = []
    if not primary_df.empty:
        for _, row in primary_df.iterrows():
            year = row.get('year')
            rating = row.get('rating')
            if pd.notna(rating) and pd.notna(year):
                year_rating_pairs.append((int(year), float(rating)))

    if len(year_rating_pairs) > 10:
        years_arr = np.array([p[0] for p in year_rating_pairs])
        ratings_arr = np.array([p[1] for p in year_rating_pairs])
        corr = float(np.corrcoef(years_arr, ratings_arr)[0, 1])
        results["release_year_rating_correlation"] = round(corr, 3)

        if corr > 0.2:
            results["correlation_insight"] = "You tend to rate newer films higher."
        elif corr < -0.2:
            results["correlation_insight"] = "You tend to rate older films higher."
        else:
            results["correlation_insight"] = "Your ratings are not significantly influenced by release year."
    else:
        results["release_year_rating_correlation"] = None
        results["correlation_insight"] = None

    # ─── Heatmap Calendar Data ───
    heatmap_data = {}
    if not diary_df.empty and 'watched_date' in diary_df.columns:
        valid = diary_df.dropna(subset=['watched_date'])
        counts = valid['watched_date'].dt.date.value_counts()
        heatmap_data = {str(k): int(v) for k, v in counts.items()}
    results["heatmap_calendar"] = heatmap_data

    # ─── Rating Bias Detection ───
    if all_ratings_list:
        avg = sum(all_ratings_list) / len(all_ratings_list)
        median = float(np.median(all_ratings_list))
        mode_val = float(pd.Series(all_ratings_list).mode().iloc[0]) if all_ratings_list else 0
        high_pct = len([r for r in all_ratings_list if r >= 4.0]) / len(all_ratings_list) * 100
        low_pct = len([r for r in all_ratings_list if r <= 2.0]) / len(all_ratings_list) * 100

        bias = "neutral"
        if avg >= 3.8:
            bias = "generous"
        elif avg <= 2.5:
            bias = "harsh"
        elif high_pct > 60:
            bias = "generous"
        elif low_pct > 40:
            bias = "harsh"

        results["rating_bias"] = {
            "average": round(avg, 2),
            "median": round(median, 2),
            "mode": round(mode_val, 2),
            "high_rating_pct": round(high_pct, 1),
            "low_rating_pct": round(low_pct, 1),
            "bias_label": bias,
        }
    else:
        results["rating_bias"] = None

    return results


def compute_community_comparison(enriched_movies: list[dict],
                                  ratings_df: pd.DataFrame) -> dict:
    """Compare user ratings vs TMDB community ratings (vote_average)."""
    comparisons = []
    name_col = 'name' if 'name' in ratings_df.columns else 'title'

    # Build lookup: title_lower -> user_rating
    user_ratings = {}
    if not ratings_df.empty and 'rating' in ratings_df.columns:
        for _, row in ratings_df.iterrows():
            title = str(row.get(name_col, '')).strip().lower()
            r = row.get('rating')
            if pd.notna(r):
                user_ratings[title] = float(r)

    for m in enriched_movies:
        tmdb = m.get("tmdb")
        if not tmdb:
            continue
        title = m.get("title", "")
        user_r = user_ratings.get(title.strip().lower())
        if user_r is None:
            continue
        vote_avg = tmdb.get("vote_average")
        if vote_avg is None or vote_avg == 0:
            continue

        tmdb_r_5 = round(float(vote_avg) / 2, 2)  # Convert 0-10 to 0-5
        diff = round(user_r - tmdb_r_5, 2)

        comparisons.append({
            "title": tmdb.get("title", title),
            "year": tmdb.get("year"),
            "poster_path": tmdb.get("poster_path"),
            "user_rating": user_r,
            "tmdb_rating": tmdb_r_5,
            "difference": diff,
        })

    # Sort by difference
    rated_higher = sorted([c for c in comparisons if c["difference"] > 0],
                          key=lambda x: x["difference"], reverse=True)[:10]
    rated_lower = sorted([c for c in comparisons if c["difference"] < 0],
                         key=lambda x: x["difference"])[:10]

    return {
        "rated_higher": rated_higher,
        "rated_lower": rated_lower,
    }


def compute_binge_stats(diary_df: pd.DataFrame) -> dict:
    """Multi-film day detection and binge watching stats."""
    if diary_df.empty or 'watched_date' not in diary_df.columns:
        return {
            "multi_film_days": 0,
            "max_films_in_day": 0,
            "most_intense_day": None,
            "avg_films_per_active_day": 0,
        }

    valid = diary_df.dropna(subset=['watched_date'])
    day_counts = valid['watched_date'].dt.date.value_counts()

    total_active_days = len(day_counts)
    total_films = int(day_counts.sum())
    multi_film_days = int((day_counts >= 2).sum())
    max_films = int(day_counts.max()) if not day_counts.empty else 0
    most_intense = str(day_counts.idxmax()) if not day_counts.empty else None
    avg_per_day = round(total_films / total_active_days, 1) if total_active_days > 0 else 0

    return {
        "multi_film_days": multi_film_days,
        "max_films_in_day": max_films,
        "most_intense_day": most_intense,
        "avg_films_per_active_day": avg_per_day,
    }


def compute_monthly_activity(enriched_movies: list[dict],
                              diary_df: pd.DataFrame) -> list[dict]:
    """Build monthly film strip data with posters and stats."""
    if diary_df.empty or 'watched_date' not in diary_df.columns:
        return []

    month_names = ['January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']

    # Build TMDB lookup for posters
    tmdb_lookup = {}
    for m in enriched_movies:
        tmdb = m.get("tmdb")
        if tmdb:
            key = m.get("title", "").strip().lower()
            tmdb_lookup[key] = tmdb

    valid = diary_df.dropna(subset=['watched_date']).copy()
    valid['year_month'] = valid['watched_date'].dt.to_period('M')

    name_col = 'name' if 'name' in valid.columns else 'title'
    result = []

    for period, group in sorted(valid.groupby('year_month'), key=lambda x: x[0]):
        yr = period.year
        mo = period.month

        # Films watched this month
        films_list = []
        for _, row in group.iterrows():
            title = str(row.get(name_col, ''))
            rating = row.get('rating')
            tmdb = tmdb_lookup.get(title.strip().lower(), {})
            films_list.append({
                "title": title,
                "user_rating": float(rating) if pd.notna(rating) else None,
                "poster_path": tmdb.get("poster_path"),
            })

        # Deduplicate posters (keep first occurrence, limit to 12)
        seen_titles = set()
        unique_films = []
        for f in films_list:
            t_lower = f["title"].lower()
            if t_lower not in seen_titles and f["poster_path"]:
                seen_titles.add(t_lower)
                unique_films.append(f)
            if len(unique_films) >= 12:
                break

        # Day counts for binge peak
        day_counts = group['watched_date'].dt.date.value_counts()
        max_day_count = int(day_counts.max()) if not day_counts.empty else 0
        intense_day = str(day_counts.idxmax()) if not day_counts.empty else None

        # Avg rating
        rated = [float(r) for r in group['rating'].dropna()] if 'rating' in group.columns else []
        avg_r = round(sum(rated) / len(rated), 2) if rated else None

        result.append({
            "year": yr,
            "month": month_names[mo - 1],
            "total_films": len(group),
            "avg_rating": avg_r,
            "most_intense_day": intense_day,
            "max_films_in_day": max_day_count,
            "films": unique_films,
        })

    # Most recent months first
    result.reverse()
    return result


def compute_decade_leaderboard(enriched_movies: list[dict],
                                decade_ratings: dict) -> list[dict]:
    """Build decade leaderboard with top 3 decades (min 5 films) and poster thumbnails."""
    # decade_ratings: {1990: [4.0, 3.5, ...], ...}
    # Build poster lookup per decade
    decade_posters = defaultdict(list)
    for m in enriched_movies:
        tmdb = m.get("tmdb")
        if tmdb and tmdb.get("year") and tmdb.get("poster_path"):
            dec = int(int(tmdb["year"]) // 10 * 10)
            decade_posters[dec].append(tmdb["poster_path"])

    leaderboard = []
    for dec, ratings in decade_ratings.items():
        if len(ratings) < 5:
            continue
        avg = round(sum(ratings) / len(ratings), 2)
        posters = decade_posters.get(dec, [])[:3]  # Top 3 posters
        leaderboard.append({
            "decade": f"{dec}s",
            "avg_rating": avg,
            "film_count": len(ratings),
            "top_posters": [{"poster_path": p} for p in posters],
        })

    # Sort by avg_rating desc
    leaderboard.sort(key=lambda x: x["avg_rating"], reverse=True)
    return leaderboard[:5]  # Top 5

