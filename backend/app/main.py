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

# CORS for local React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*",],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes
app.include_router(router, prefix="/api")
