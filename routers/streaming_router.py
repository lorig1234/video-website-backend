# routers/streaming_router.py
"""
Streaming API Router

This module handles video streaming endpoints:
- Stream video with range request support
- Efficient chunked streaming
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, Response
import os
import re

router = APIRouter(prefix="/api/stream", tags=["Streaming"])


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
    "/{episode_id}",
    summary="Stream video episode",
    description="""
    Stream a video episode with support for range requests (seeking).
    
    **🔓 No Authentication Required** (for video playback)
    
    **Parameters:**
    - `episode_id`: The unique episode identifier (e.g., "breaking_bad_s01_e1")
    
    **Features:**
    - Supports HTTP Range requests for seeking
    - Chunked streaming for efficient bandwidth usage
    - Progressive chunk size (64KB → 256KB → 1MB)
    - Proper CORS headers for cross-origin playback
    
    **Headers Returned:**
    - `Content-Range`: Byte range being served
    - `Accept-Ranges`: bytes
    - `Content-Type`: video/mp4
    
    **Usage:**
    ```html
    <video src="http://localhost:8087/api/stream/breaking_bad_s01_e1" controls></video>
    ```
    
    **Note:** 
    - Range header is optional but recommended for seeking
    - Without Range header, entire file is served
    - With Range header, returns 206 Partial Content
    """,
    response_description="Video stream",
    responses={
        200: {
            "description": "Full video file (no range header)",
            "content": {
                "video/mp4": {}
            }
        },
        206: {
            "description": "Partial content (with range header)",
            "headers": {
                "Content-Range": {
                    "description": "Byte range being served",
                    "schema": {"type": "string", "example": "bytes 0-1048575/52428800"}
                },
                "Accept-Ranges": {
                    "description": "Indicates range support",
                    "schema": {"type": "string", "example": "bytes"}
                }
            },
            "content": {
                "video/mp4": {}
            }
        },
        404: {
            "description": "Episode or file not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Episode not found"}
                }
            }
        },
        416: {
            "description": "Range not satisfiable (malformed range header)"
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Internal server error"}
                }
            }
        }
    }
)
async def stream_video(episode_id: str, request: Request):
    """Stream video with range request support"""
    shows = get_shows_data()
    
    try:
        # Find the show and episode from the ID
        # ID format can be: show_id_episode or show_id_sXX_eYY
        
        # Extract show_id (everything before _s or last _)
        match = re.match(r'^([^_]+(?:_[^_]+)*?)(?:_s\d+_e\d+|_\d+)$', episode_id)
        if match:
            show_id = match.group(1)
        else:
            # Fallback to old method
            show_id = episode_id.rsplit('_', 1)[0]
        
        show = next((s for s in shows if s["id"] == show_id), None)
        
        if not show:
            print(f"Show not found for ID: {show_id}")
            raise HTTPException(status_code=404, detail="Show not found")
            
        # Search for the episode in all seasons
        episode = None
        for season in show["seasons"]:
            episode = next((ep for ep in season["episodes"] if ep["id"] == episode_id), None)
            if episode:
                break
                
        if not episode:
            print(f"Episode not found for ID: {episode_id}")
            raise HTTPException(status_code=404, detail="Episode not found")
        
        # Only log when starting a new video (no range header)
        if not request.headers.get("range"):
            print(f"New stream started - Show: {show['title']}, Episode: {episode['title']}")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in stream_video: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
        
    path = episode["file"]
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Video file not found")

    file_size = os.path.getsize(path)
    if not request.headers.get("range"):  # Only log when starting a new video
        print(f"New stream: {os.path.basename(path)}")
    
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
        # Malformed range
        return Response(status_code=416)

    def iter_file(p, start_pos, end_pos, initial_block_size=64*1024):
        """Generator to stream file chunks"""
        with open(p, "rb") as f:
            try:
                f.seek(start_pos)
                bytes_left = (end_pos - start_pos) + 1
                chunks_sent = 0
                
                while bytes_left > 0:
                    # Increase block size gradually for better streaming
                    if chunks_sent < 10:
                        block_size = initial_block_size  # 64KB
                    elif chunks_sent < 20:
                        block_size = initial_block_size * 4  # 256KB
                    else:
                        block_size = initial_block_size * 16  # 1MB

                    read_size = min(block_size, bytes_left)
                    chunk = f.read(read_size)
                    if not chunk:
                        break
                    
                    bytes_left -= len(chunk)
                    chunks_sent += 1
                    yield chunk
            except (ConnectionError, BrokenPipeError):
                # Client disconnected - stop streaming silently
                return
            except Exception as e:
                # Log any other errors
                print(f"Error streaming file: {e}")

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
