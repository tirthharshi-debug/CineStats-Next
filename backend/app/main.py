"""
FastAPI application entry point.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import os

# Load environment variables from project root
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from app.database.db import init_db
from app.routes.api import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    await init_db()
    print("[OK] Database initialized")
    print(f"[Key] TMDB API key loaded: {'Yes' if os.getenv('TMDB_API_KEY') else 'No'}")
    yield
    print("[Down] Shutting down...")


app = FastAPI(
    title="Letterboxd Analytics",
    description="Analyze your Letterboxd export with TMDB-enriched analytics",
    version="1.0.0",
    lifespan=lifespan,
)

# Only allow configured frontend origins. Set CORS_ALLOWED_ORIGINS on deployment,
# for example: https://your-app.vercel.app,https://your-custom-domain.example
_allowed_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "X-Job-Token"],
)

# Mount routes
app.include_router(router, prefix="/api")
