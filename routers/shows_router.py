# routers/shows_router.py
"""
Shows API Router

This module handles all show-related endpoints:
- List all shows
- Get show details with episodes
- Show search/filtering
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from typing import List, Optional
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/shows", tags=["Shows"])


# ============== Pydantic Models ==============

class Episode(BaseModel):
    """Episode information"""
    id: str = Field(..., description="Unique episode identifier", example="breaking_bad_s01_e1")
    title: str = Field(..., description="Episode title", example="Pilot")
    number: int = Field(..., description="Episode number within season", example=1)
    season: str = Field(..., description="Season identifier", example="S01")


class Season(BaseModel):
    """Season information with episodes"""
    year: str = Field(..., description="Season identifier", example="S01")
    episodeCount: int = Field(..., description="Number of episodes", example=7)
    episodes: List[Episode] = Field(..., description="List of episodes")


class ShowSummary(BaseModel):
    """Show summary for listing"""
    id: str = Field(..., description="Unique show identifier", example="breaking_bad")
    title: str = Field(..., description="Show title", example="Breaking Bad")
    episodeCount: int = Field(..., description="Total episodes", example=62)
    poster: str = Field(..., description="Poster image URL", example="/posters/breaking_bad.jpg")


class ShowDetails(BaseModel):
    """Full show details with seasons and episodes"""
    id: str
    title: str
    episodeCount: int
    seasonCount: int
    poster: str
    seasons: List[Season]


# Store reference to SHOWS (will be set by main server)
SHOWS = []

def set_shows(shows_data: list):
    """Set the shows data from main server"""
    global SHOWS
    SHOWS = shows_data


def get_shows_data():
    """Get current shows data"""
    return SHOWS


# ============== API Endpoints ==============

@router.get(
    "",
    summary="Get all shows",
    description="""
    Get a list of all available shows.
    
    **🔓 No Authentication Required**
    
    **Returns:**
    - List of all shows with basic information
    - Includes show ID, title, episode count, and poster URL
    - Does NOT include episode details (use `/api/shows/{show_id}` for that)
    
    **Note:** If no shows are found in the video library, dummy data is returned for demonstration.
    """,
    response_description="List of all shows",
    responses={
        200: {
            "description": "Shows retrieved successfully",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "breaking_bad",
                            "title": "Breaking Bad",
                            "episodeCount": 62,
                            "poster": "http://localhost:8087/posters/breaking_bad.jpg"
                        },
                        {
                            "id": "stranger_things",
                            "title": "Stranger Things",
                            "episodeCount": 42,
                            "poster": "http://localhost:8087/posters/stranger_things.jpg"
                        }
                    ]
                }
            }
        }
    }
)
def get_shows():
    """Get list of all available shows"""
    shows = get_shows_data()
    
    # Return dummy data if no real shows are found
    if not shows:
        dummy_shows = [
            {
                "id": "breaking_bad",
                "title": "Breaking Bad", 
                "episodeCount": 62,
                "poster": "http://localhost:8087/posters/breaking_bad.jpg"
            },
            {
                "id": "stranger_things",
                "title": "Stranger Things",
                "episodeCount": 42, 
                "poster": "http://localhost:8087/posters/stranger_things.jpg"
            },
            {
                "id": "the_office",
                "title": "The Office",
                "episodeCount": 201,
                "poster": "http://localhost:8087/posters/the_office.jpg"
            },
            {
                "id": "game_of_thrones",
                "title": "Game of Thrones",
                "episodeCount": 73,
                "poster": "http://localhost:8087/posters/game_of_thrones.jpg"
            },
            {
                "id": "friends",
                "title": "Friends", 
                "episodeCount": 236,
                "poster": "http://localhost:8087/posters/friends.jpg"
            },
            {
                "id": "the_mandalorian",
                "title": "The Mandalorian",
                "episodeCount": 24,
                "poster": "http://localhost:8087/posters/the_mandalorian.jpg"
            }
        ]
        return JSONResponse(dummy_shows)
    
    # Return real show data
    show_list = [{
        "id": show["id"],
        "title": show["title"],
        "episodeCount": show["episodeCount"],
        "poster": show["poster"]
    } for show in shows]
    return JSONResponse(show_list)


@router.get(
    "/{show_id}",
    summary="Get show details",
    description="""
    Get detailed information about a specific show including all seasons and episodes.
    
    **🔓 No Authentication Required**
    
    **Parameters:**
    - `show_id`: The unique identifier of the show (e.g., "breaking_bad")
    
    **Returns:**
    - Full show details including:
      - Show metadata (title, poster, counts)
      - All seasons with episode lists
      - Episode IDs needed for streaming
    
    **Note:** If show not found in library but exists in dummy data, returns dummy data.
    """,
    response_description="Show details with episodes",
    responses={
        200: {
            "description": "Show details retrieved",
            "content": {
                "application/json": {
                    "example": {
                        "id": "breaking_bad",
                        "title": "Breaking Bad",
                        "episodeCount": 6,
                        "seasonCount": 2,
                        "poster": "http://localhost:8087/posters/breaking_bad.jpg",
                        "seasons": [
                            {
                                "year": "S01",
                                "episodeCount": 3,
                                "episodes": [
                                    {"id": "breaking_bad_s01_e1", "title": "Pilot", "number": 1, "season": "S01"},
                                    {"id": "breaking_bad_s01_e2", "title": "Cat's in the Bag...", "number": 2, "season": "S01"},
                                    {"id": "breaking_bad_s01_e3", "title": "...And the Bag's in the River", "number": 3, "season": "S01"}
                                ]
                            }
                        ]
                    }
                }
            }
        },
        404: {
            "description": "Show not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Show not found"}
                }
            }
        }
    }
)
def get_show_details(show_id: str):
    """Get detailed information about a specific show"""
    shows = get_shows_data()
    show = next((s for s in shows if s["id"] == show_id), None)
    
    if not show:
        # Return dummy show details if no real shows are found
        dummy_shows = {
            "breaking_bad": {
                "id": "breaking_bad",
                "title": "Breaking Bad",
                "episodeCount": 6,
                "seasonCount": 2,
                "poster": "http://localhost:8087/posters/breaking_bad.jpg",
                "seasons": [
                    {
                        "year": "S01",
                        "episodeCount": 3,
                        "episodes": [
                            {"id": "breaking_bad_s01_e1", "title": "Pilot", "number": 1, "season": "S01", "file": "dummy.mp4"},
                            {"id": "breaking_bad_s01_e2", "title": "Cat's in the Bag...", "number": 2, "season": "S01", "file": "dummy.mp4"},
                            {"id": "breaking_bad_s01_e3", "title": "...And the Bag's in the River", "number": 3, "season": "S01", "file": "dummy.mp4"}
                        ]
                    },
                    {
                        "year": "S02", 
                        "episodeCount": 3,
                        "episodes": [
                            {"id": "breaking_bad_s02_e1", "title": "Seven Thirty-Seven", "number": 1, "season": "S02", "file": "dummy.mp4"},
                            {"id": "breaking_bad_s02_e2", "title": "Grilled", "number": 2, "season": "S02", "file": "dummy.mp4"},
                            {"id": "breaking_bad_s02_e3", "title": "Bit by a Dead Bee", "number": 3, "season": "S02", "file": "dummy.mp4"}
                        ]
                    }
                ]
            },
            "stranger_things": {
                "id": "stranger_things",
                "title": "Stranger Things", 
                "episodeCount": 4,
                "seasonCount": 1,
                "poster": "http://localhost:8087/posters/stranger_things.jpg",
                "seasons": [
                    {
                        "year": "S01",
                        "episodeCount": 4,
                        "episodes": [
                            {"id": "stranger_things_s01_e1", "title": "The Vanishing of Will Byers", "number": 1, "season": "S01", "file": "dummy.mp4"},
                            {"id": "stranger_things_s01_e2", "title": "The Weirdo on Maple Street", "number": 2, "season": "S01", "file": "dummy.mp4"},
                            {"id": "stranger_things_s01_e3", "title": "Holly, Jolly", "number": 3, "season": "S01", "file": "dummy.mp4"},
                            {"id": "stranger_things_s01_e4", "title": "The Body", "number": 4, "season": "S01", "file": "dummy.mp4"}
                        ]
                    }
                ]
            }
        }
        
        if show_id in dummy_shows:
            return JSONResponse(dummy_shows[show_id])
        else:
            raise HTTPException(status_code=404, detail="Show not found")
    
    return JSONResponse(show)
