# routers/movies_router.py
"""
Movies API Router

This module handles all movie-related endpoints:
- List all movies
- Get movie details
- Stream a movie
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse, Response
import os
import re

router = APIRouter(prefix="/api/movies", tags=["Movies"])


# ============== Data Store ==============

MOVIES = []

def set_movies(movies_data: list):
    """Set the movies data from main server"""
    global MOVIES
    MOVIES = movies_data


def get_movies_data():
    """Get current movies data"""
    return MOVIES


# ============== API Endpoints ==============

@router.get(
    "",
    summary="Get all movies",
    description="Get a list of all available movies. No authentication required.",
    response_description="List of all movies",
)
def get_movies():
    """Get list of all available movies"""
    movies = get_movies_data()
    movie_list = [{
        "id": m["id"],
        "title": m["title"],
        "year": m["year"],
        "poster": m["poster"]
    } for m in movies]
    return JSONResponse(movie_list)


@router.get(
    "/{movie_id}",
    summary="Get movie details",
    description="Get detailed information about a specific movie.",
    response_description="Movie details",
)
def get_movie_details(movie_id: str):
    """Get details for a specific movie"""
    movies = get_movies_data()
    movie = next((m for m in movies if m["id"] == movie_id), None)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    # Return everything except the raw file path
    return JSONResponse({
        "id": movie["id"],
        "title": movie["title"],
        "year": movie["year"],
        "poster": movie["poster"]
    })


@router.get(
    "/poster/{movie_id}",
    summary="Get movie poster",
    description="Serve the poster image from the movie's folder.",
    response_description="Poster image",
)
async def get_movie_poster(movie_id: str):
    """Serve poster image found inside the movie folder"""
    movies = get_movies_data()
    movie = next((m for m in movies if m["id"] == movie_id), None)
    if not movie or not movie.get("poster_file"):
        raise HTTPException(status_code=404, detail="Poster not found")
    path = movie["poster_file"]
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Poster file not found on disk")
    media = "image/jpeg"
    if path.lower().endswith(".png"):
        media = "image/png"
    return FileResponse(path, media_type=media)


@router.get(
    "/stream/{movie_id}",
    summary="Stream a movie",
    description="Stream a movie with HTTP range request support for seeking.",
    response_description="Video stream",
)
async def stream_movie(movie_id: str, request: Request):
    """Stream movie with range request support"""
    movies = get_movies_data()
    movie = next((m for m in movies if m["id"] == movie_id), None)

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    path = movie["file"]
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Movie file not found on disk")

    file_size = os.path.getsize(path)

    if not request.headers.get("range"):
        print(f"New movie stream: {movie['title']}")

    range_header = request.headers.get("range")
    if range_header is None:
        return FileResponse(path, media_type="video/mp4")

    # Parse Range: bytes=start-end
    try:
        _, rng = range_header.split("=")
        start_str, end_str = (rng.split("-") + [""])[:2]
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
        start = max(0, start)
        end = min(end, file_size - 1)
        chunk_size = (end - start) + 1
    except Exception:
        return Response(status_code=416)

    def iter_file(p, start_pos, end_pos, initial_block_size=64*1024):
        with open(p, "rb") as f:
            try:
                f.seek(start_pos)
                bytes_left = (end_pos - start_pos) + 1
                chunks_sent = 0
                while bytes_left > 0:
                    if chunks_sent < 10:
                        block_size = initial_block_size
                    elif chunks_sent < 20:
                        block_size = initial_block_size * 4
                    else:
                        block_size = initial_block_size * 16
                    read_size = min(block_size, bytes_left)
                    chunk = f.read(read_size)
                    if not chunk:
                        break
                    bytes_left -= len(chunk)
                    chunks_sent += 1
                    yield chunk
            except (ConnectionError, BrokenPipeError):
                return
            except Exception as e:
                print(f"Error streaming movie: {e}")

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_size),
        "Content-Type": "video/mp4",
        "Cache-Control": "public, max-age=3600, stale-while-revalidate=86400",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Expose-Headers": "Content-Range, Accept-Ranges, Content-Length",
        "Connection": "keep-alive"
    }
    return StreamingResponse(iter_file(path, start, end), status_code=206, headers=headers)
