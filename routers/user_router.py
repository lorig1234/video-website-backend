# routers/user_router.py
"""
User API Router

This module handles all user-related endpoints:
- Watch progress (save/retrieve)
- Continue watching
- Watch history
- User IP addresses
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List

import database as db
from auth import require_auth

router = APIRouter(prefix="/api/user", tags=["User"])


# ============== Pydantic Models ==============

class WatchProgressUpdate(BaseModel):
    """Request model for updating watch progress"""
    show_id: str = Field(
        ...,
        description="Unique identifier of the show",
        example="breaking_bad"
    )
    episode_id: str = Field(
        ...,
        description="Unique identifier of the episode",
        example="breaking_bad_s01_e1"
    )
    position_seconds: int = Field(
        ...,
        ge=0,
        description="Current playback position in seconds",
        example=1234
    )
    duration_seconds: int = Field(
        ...,
        ge=0,
        description="Total duration of the episode in seconds",
        example=3600
    )
    show_title: Optional[str] = Field(
        None,
        description="Title of the show (for display purposes)",
        example="Breaking Bad"
    )
    episode_title: Optional[str] = Field(
        None,
        description="Title of the episode (for display purposes)",
        example="Pilot"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "show_id": "breaking_bad",
                "episode_id": "breaking_bad_s01_e1",
                "position_seconds": 1234,
                "duration_seconds": 3600,
                "show_title": "Breaking Bad",
                "episode_title": "Pilot"
            }
        }


class WatchProgressResponse(BaseModel):
    """Watch progress information"""
    position_seconds: int
    duration_seconds: int
    progress_percent: float


class ContinueWatchingItem(BaseModel):
    """Item in continue watching list"""
    show_id: str
    episode_id: str
    show_title: Optional[str]
    episode_title: Optional[str]
    position_seconds: int
    duration_seconds: int
    progress_percent: float
    watched_at: str


class UserIPInfo(BaseModel):
    """User IP address information"""
    ip_address: str
    first_seen: str
    last_seen: str
    access_count: int


# ============== API Endpoints ==============

@router.post(
    "/watch-progress",
    summary="Save watch progress",
    description="""
    Save the current playback position for an episode.
    
    **🔒 Authentication Required**
    
    Include your token in the Authorization header:
    ```
    Authorization: Bearer <your_token>
    ```
    
    **Usage:**
    - Call this endpoint periodically while user is watching (e.g., every 10 seconds)
    - Call when user pauses or leaves the video
    - Progress is stored per user per episode
    
    **Progress Tracking:**
    - Episodes with < 95% progress appear in "Continue Watching"
    - Progress >= 95% is considered "completed"
    """,
    response_description="Progress saved successfully",
    responses={
        200: {
            "description": "Progress saved",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Progress saved"
                    }
                }
            }
        },
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {
                    "example": {"detail": "Not authenticated"}
                }
            }
        }
    }
)
async def update_watch_progress(
    progress: WatchProgressUpdate,
    current_user: dict = Depends(require_auth)
):
    """Save user's watch progress for an episode"""
    db.save_watch_progress(
        user_id=current_user["id"],
        show_id=progress.show_id,
        episode_id=progress.episode_id,
        position_seconds=progress.position_seconds,
        duration_seconds=progress.duration_seconds,
        show_title=progress.show_title,
        episode_title=progress.episode_title
    )
    return JSONResponse({
        "success": True,
        "message": "Progress saved"
    })


@router.get(
    "/watch-progress/{episode_id}",
    summary="Get watch progress for episode",
    description="""
    Get the saved playback position for a specific episode.
    
    **🔒 Authentication Required**
    
    Include your token in the Authorization header:
    ```
    Authorization: Bearer <your_token>
    ```
    
    **Usage:**
    - Call when loading the video player to resume from last position
    - Returns `null` progress if episode hasn't been watched
    """,
    response_description="Episode progress information",
    responses={
        200: {
            "description": "Progress retrieved",
            "content": {
                "application/json": {
                    "examples": {
                        "has_progress": {
                            "summary": "Episode has saved progress",
                            "value": {
                                "success": True,
                                "progress": {
                                    "position_seconds": 1234,
                                    "duration_seconds": 3600,
                                    "progress_percent": 34.28
                                }
                            }
                        },
                        "no_progress": {
                            "summary": "Episode not watched yet",
                            "value": {
                                "success": True,
                                "progress": None
                            }
                        }
                    }
                }
            }
        },
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {
                    "example": {"detail": "Not authenticated"}
                }
            }
        }
    }
)
async def get_watch_progress(
    episode_id: str,
    current_user: dict = Depends(require_auth)
):
    """Get watch progress for a specific episode"""
    progress = db.get_watch_progress(current_user["id"], episode_id)
    if progress:
        return JSONResponse({
            "success": True,
            "progress": {
                "position_seconds": progress["position_seconds"],
                "duration_seconds": progress["duration_seconds"],
                "progress_percent": progress["progress_percent"]
            }
        })
    return JSONResponse({
        "success": True,
        "progress": None
    })


@router.get(
    "/continue-watching",
    summary="Get continue watching list",
    description="""
    Get list of episodes that the user started watching but hasn't finished (< 95% progress).
    
    **🔒 Authentication Required**
    
    Include your token in the Authorization header:
    ```
    Authorization: Bearer <your_token>
    ```
    
    **Returns:**
    - Up to 10 most recently watched, unfinished episodes
    - Sorted by most recently watched first
    - Includes progress information for each episode
    
    **Use Case:**
    - Display "Continue Watching" section on homepage
    """,
    response_description="List of unfinished episodes",
    responses={
        200: {
            "description": "Continue watching list",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "items": [
                            {
                                "id": 1,
                                "user_id": 1,
                                "show_id": "breaking_bad",
                                "episode_id": "breaking_bad_s01_e1",
                                "show_title": "Breaking Bad",
                                "episode_title": "Pilot",
                                "position_seconds": 1234,
                                "duration_seconds": 3600,
                                "progress_percent": 34.28,
                                "watched_at": "2025-01-19T12:00:00"
                            }
                        ]
                    }
                }
            }
        },
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {
                    "example": {"detail": "Not authenticated"}
                }
            }
        }
    }
)
async def get_continue_watching(current_user: dict = Depends(require_auth)):
    """Get list of shows to continue watching"""
    items = db.get_continue_watching(current_user["id"])
    return JSONResponse({
        "success": True,
        "items": items
    })


@router.get(
    "/watch-history",
    summary="Get full watch history",
    description="""
    Get the user's complete watch history.
    
    **🔒 Authentication Required**
    
    Include your token in the Authorization header:
    ```
    Authorization: Bearer <your_token>
    ```
    
    **Returns:**
    - Up to 50 most recently watched episodes
    - Includes both completed and in-progress episodes
    - Sorted by most recently watched first
    
    **Use Case:**
    - Display watch history page
    - Analytics and recommendations
    """,
    response_description="Full watch history",
    responses={
        200: {
            "description": "Watch history list",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "history": [
                            {
                                "id": 1,
                                "user_id": 1,
                                "show_id": "breaking_bad",
                                "episode_id": "breaking_bad_s01_e1",
                                "show_title": "Breaking Bad",
                                "episode_title": "Pilot",
                                "position_seconds": 3400,
                                "duration_seconds": 3600,
                                "progress_percent": 94.44,
                                "watched_at": "2025-01-19T12:00:00"
                            }
                        ]
                    }
                }
            }
        },
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {
                    "example": {"detail": "Not authenticated"}
                }
            }
        }
    }
)
async def get_watch_history(current_user: dict = Depends(require_auth)):
    """Get user's full watch history"""
    history = db.get_watch_history(current_user["id"])
    return JSONResponse({
        "success": True,
        "history": history
    })


@router.get(
    "/ips",
    summary="Get user's IP addresses",
    description="""
    Get all IP addresses that this user has connected from.
    
    **🔒 Authentication Required**
    
    Include your token in the Authorization header:
    ```
    Authorization: Bearer <your_token>
    ```
    
    **Returns:**
    - List of all IPs with timestamps
    - First and last access time for each IP
    - Access count per IP
    
    **Use Case:**
    - Security monitoring
    - Detect suspicious activity
    - Account security page
    """,
    response_description="List of IP addresses",
    responses={
        200: {
            "description": "IP addresses list",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "ips": [
                            {
                                "ip_address": "192.168.1.100",
                                "first_seen": "2025-01-15T10:00:00",
                                "last_seen": "2025-01-19T12:00:00",
                                "access_count": 42
                            },
                            {
                                "ip_address": "10.0.0.50",
                                "first_seen": "2025-01-18T15:30:00",
                                "last_seen": "2025-01-18T18:45:00",
                                "access_count": 5
                            }
                        ]
                    }
                }
            }
        },
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {
                    "example": {"detail": "Not authenticated"}
                }
            }
        }
    }
)
async def get_user_ips(current_user: dict = Depends(require_auth)):
    """Get all IPs this user has connected from"""
    ips = db.get_user_ips(current_user["id"])
    return JSONResponse({
        "success": True,
        "ips": ips
    })


@router.get(
    "/last-episode-per-show",
    summary="Get last watched episode for each show",
    description="""
    Get the most recently watched episode for each show.
    
    **🔒 Authentication Required**
    
    Include your token in the Authorization header:
    ```
    Authorization: Bearer <your_token>
    ```
    
    **Returns:**
    - Dictionary mapping show_id to the last watched episode info
    - Useful for displaying "Continue watching from S02E05" on show cards
    - Includes progress information and timestamps
    
    **Use Case:**
    - Show "Continue watching" indicators on show thumbnails
    - Display last watched episode info when user hovers over a show
    """,
    response_description="Last episode per show",
    responses={
        200: {
            "description": "Last watched episodes by show",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": {
                            "breaking_bad": {
                                "episode_id": "breaking_bad_s02_e05",
                                "episode_title": "Breakage",
                                "position_seconds": 1800,
                                "duration_seconds": 3600,
                                "progress_percent": 50.0,
                                "watched_at": "2025-01-19T12:00:00"
                            },
                            "friends": {
                                "episode_id": "friends_s01_e03",
                                "episode_title": "The One with the Thumb",
                                "position_seconds": 300,
                                "duration_seconds": 1320,
                                "progress_percent": 22.73,
                                "watched_at": "2025-01-18T20:30:00"
                            }
                        }
                    }
                }
            }
        },
        401: {
            "description": "Not authenticated",
            "content": {
                "application/json": {
                    "example": {"detail": "Not authenticated"}
                }
            }
        }
    }
)
async def get_last_episode_per_show(current_user: dict = Depends(require_auth)):
    """Get the last watched episode for each show"""
    data = db.get_last_episode_per_show(current_user["id"])
    return JSONResponse({
        "success": True,
        "data": data
    })
