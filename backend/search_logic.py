import os
import requests
from dotenv import load_dotenv

load_dotenv()

TMDB_API_URL = "https://api.themoviedb.org/3/search/multi"
TMDB_DETAILS_URL = "https://api.themoviedb.org/3"
TMDB_GENRES_URL = "https://api.themoviedb.org/3/genre/movie/list"
TMDB_DISCOVER_URL = "https://api.themoviedb.org/3/discover/movie"


def _api_key():
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key or api_key.startswith("replace-with-"):
        raise RuntimeError("TMDB_API_KEY is not configured")
    return api_key


def search_movies(query):
    response = requests.get(
        TMDB_API_URL,
        params={
            "api_key": _api_key(),
            "query": query,
            "page": 1,
            "include_adult": False,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json().get("results", [])


def get_title_details(media_type, item_id):
    if media_type not in {"movie", "tv", "person", "collection", "episode", "season", "company", "series"}:
        raise ValueError("Unsupported media type")

    response = requests.get(
        f"{TMDB_DETAILS_URL}/{media_type}/{item_id}",
        params={"api_key": _api_key()},
        timeout=10,
    )
    response.raise_for_status()
    details = response.json()
    details["media_type"] = media_type
    return details


def get_movie_genres():
    response = requests.get(
        TMDB_GENRES_URL,
        params={"api_key": _api_key(), "language": "en-US"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json().get("genres", [])


def discover_movies(genre_id, page=1):
    response = requests.get(
        TMDB_DISCOVER_URL,
        params={
            "api_key": _api_key(),
            "with_genres": genre_id,
            "page": page,
            "sort_by": "popularity.desc",
            "include_adult": False,
            "language": "en-US",
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


