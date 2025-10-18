# server.py
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import logging

# Configure logging
logging.getLogger("uvicorn.error").setLevel(logging.CRITICAL)  # Only show critical errors
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.asgi").setLevel(logging.WARNING)

# Create a custom filter to ignore connection reset errors
class IgnoreConnectionResetFilter(logging.Filter):
    def filter(self, record):
        return "ConnectionResetError" not in str(record.exc_info) if record.exc_info else True

# Apply the filter to the asyncio logger
asyncio_logger = logging.getLogger("asyncio")
asyncio_logger.addFilter(IgnoreConnectionResetFilter())
import ffmpeg_streaming
from ffmpeg_streaming import Formats, Representation, Size
from pathlib import Path

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create necessary directories
os.makedirs("posters", exist_ok=True)
os.makedirs("hls", exist_ok=True)

@app.get("/")
async def get_index():
    return FileResponse("index.html")

@app.get("/test")
async def get_test():
    return FileResponse("test.html")

# static files
app.mount("/posters", StaticFiles(directory="posters"), name="posters")
app.mount("/hls", StaticFiles(directory="hls"), name="hls")
app.mount("/videos", StaticFiles(directory="videos"), name="videos")

@app.get("/player")
async def get_player():
    return FileResponse("player.html")

# Function to scan videos directory and generate show data
def scan_video_directory():
    import re
    shows = []
    videos_dir = Path("videos")
    
    if not videos_dir.exists():
        return []
    
    # Scan each show directory
    for show_dir in videos_dir.iterdir():
        if show_dir.is_dir() and not show_dir.name.startswith('.'):
            show_name = show_dir.name.replace('_', ' ').title()
            show_id = show_dir.name.lower()
            
            # Get all episodes for this show
            total_episodes = []
            season_episodes = {}
            
            # Look for season folders (S01, S02, etc. or "Season 1", "Season 2", etc.) or direct video files
            season_folders = sorted([f for f in show_dir.iterdir() if f.is_dir() and (re.match(r'S\d+', f.name, re.IGNORECASE) or re.match(r'.*season\s*\d+', f.name, re.IGNORECASE))])
            
            if season_folders:
                # Process season-based structure
                for season_folder in season_folders:
                    # Extract season number - handle both "S01" and "Season 1" formats
                    if re.match(r'S\d+', season_folder.name, re.IGNORECASE):
                        season_number = season_folder.name.upper()  # S01, S02, etc.
                    else:
                        # Extract number from "Season 1" format and convert to S01
                        match = re.search(r'season\s*(\d+)', season_folder.name, re.IGNORECASE)
                        if match:
                            season_num = int(match.group(1))
                            season_number = f"S{season_num:02d}"
                        else:
                            season_number = season_folder.name.upper()
                    
                    if season_number not in season_episodes:
                        season_episodes[season_number] = []
                    
                    # Find all video files in this season
                    # Priority: .safari.mp4 > .h264.mp4 > .mp4 > .mkv > .avi for best compatibility
                    safari_files = list(season_folder.glob("*.safari.mp4"))
                    h264_files = list(season_folder.glob("*.h264.mp4"))
                    mp4_files = [f for f in season_folder.glob("*.mp4") 
                                if not f.name.endswith('.h264.mp4') 
                                and not f.name.endswith('.safari.mp4')]
                    mkv_files = list(season_folder.glob("*.mkv"))
                    avi_files = list(season_folder.glob("*.avi"))
                    
                    # Combine and sort, preferring safari > h264 > mp4 > mkv
                    all_videos = {}
                    for f in mkv_files + avi_files + mp4_files + h264_files + safari_files:
                        # Use base name without extension as key to deduplicate
                        base_name = f.stem.replace('.h264', '').replace('.safari', '')
                        # Extract episode number for proper key
                        ep_match = re.search(r'[Ss]\d+[Ee]\d+', f.name)
                        if ep_match:
                            key = ep_match.group(0)
                        else:
                            key = base_name
                        # Keep the highest priority version (safari > h264 > mp4)
                        if key not in all_videos:
                            all_videos[key] = f
                        elif f.name.endswith('.safari.mp4'):
                            all_videos[key] = f  # Safari version has highest priority
                        elif f.name.endswith('.h264.mp4') and not all_videos[key].name.endswith('.safari.mp4'):
                            all_videos[key] = f  # H264 has priority over regular mp4
                        elif f.suffix == '.mp4' and all_videos[key].suffix in ['.mkv', '.avi']:
                            all_videos[key] = f  # MP4 has priority over mkv/avi
                    
                    video_files = sorted(all_videos.values(), key=lambda x: x.name)
                    
                    for video_file in video_files:
                        episode_number = len(total_episodes) + 1
                        
                        # Extract episode info from filename (e.g., S01E01)
                        filename = video_file.stem
                        episode_match = re.search(r'[Ss]\d+[Ee](\d+)', filename)
                        episode_num_in_season = int(episode_match.group(1)) if episode_match else len(season_episodes[season_number]) + 1
                        
                        # Clean up title - remove show name, quality info, etc.
                        title = filename
                        # Remove show name from start
                        title = re.sub(rf'^{re.escape(show_name)}\.?', '', title, flags=re.IGNORECASE)
                        # Remove season/episode code
                        title = re.sub(r'[Ss]\d+[Ee]\d+\.?', '', title)
                        # Remove quality markers
                        title = re.sub(r'\d+p.*$', '', title)
                        title = re.sub(r'(BluRay|WEB-DL|HDTV|x264|x265|HEVC|PSA).*$', '', title, flags=re.IGNORECASE)
                        # Clean up dots and underscores
                        title = title.replace('.', ' ').replace('_', ' ')
                        # Remove extra spaces
                        title = ' '.join(title.split()).strip()
                        
                        if not title:
                            title = f"Episode {episode_num_in_season}"
                        
                        # Create episode object
                        episode = {
                            "id": f"{show_id}_s{season_number[1:]}_e{episode_num_in_season}",
                            "title": title,
                            "number": episode_num_in_season,
                            "season": season_number,
                            "file": str(video_file)
                        }
                        
                        season_episodes[season_number].append(episode)
                        total_episodes.append(episode)
            else:
                # Process flat structure (videos directly in show folder)
                video_files = sorted(list(show_dir.glob("*.mp4")) + 
                                   list(show_dir.glob("*.mkv")) + 
                                   list(show_dir.glob("*.avi")))
                
                for video_file in video_files:
                    episode_number = len(total_episodes) + 1
                    
                    # Create a more readable title from filename
                    title = video_file.stem.replace('_', ' ').replace('.', ' ')
                    if title.lower().startswith(show_name.lower()):
                        title = title[len(show_name):].strip()
                    
                    # Try to extract year for season grouping
                    date_match = re.search(r'20\d{2}', title)
                    season_year = date_match.group(0) if date_match else "Other"
                    
                    # Create season if it doesn't exist
                    if season_year not in season_episodes:
                        season_episodes[season_year] = []
                    
                    # Create episode object
                    episode = {
                        "id": f"{show_id}_{episode_number}",
                        "title": title,
                        "number": len(season_episodes[season_year]) + 1,
                        "season": season_year,
                        "file": str(video_file)
                    }
                    
                    season_episodes[season_year].append(episode)
                    total_episodes.append(episode)
            
            if total_episodes:  # Only add shows that have episodes
                # Sort seasons
                sorted_seasons = sorted(season_episodes.keys())
                
                # Create seasons list with episodes
                seasons = []
                for season_name in sorted_seasons:
                    season = {
                        "year": season_name,
                        "episodeCount": len(season_episodes[season_name]),
                        "episodes": sorted(season_episodes[season_name], key=lambda x: x["number"])
                    }
                    seasons.append(season)
                
                show = {
                    "id": show_id,
                    "title": show_name,
                    "episodeCount": len(total_episodes),
                    "seasonCount": len(seasons),
                    "poster": f"/posters/{show_id}.jpg",
                    "seasons": seasons
                }
                shows.append(show)
                print(f"Added show: {show_name} with {len(total_episodes)} episodes across {len(seasons)} seasons")
    
    return shows

# Initialize shows
SHOWS = scan_video_directory()

@app.get("/api/shows")
def get_shows():
    # Return just the show information without episodes for the main listing
    show_list = [{
        "id": show["id"],
        "title": show["title"],
        "episodeCount": show["episodeCount"],
        "poster": show["poster"]
    } for show in SHOWS]
    return JSONResponse(show_list)

@app.get("/api/shows/{show_id}")
def get_show_details(show_id: str):
    show = next((s for s in SHOWS if s["id"] == show_id), None)
    if not show:
        raise HTTPException(status_code=404, detail="Show not found")
    return JSONResponse(show)

@app.get("/api/stream/{id}")
async def stream_video(id: str, request: Request):
    try:
        # Find the show and episode from the ID
        # ID format can be: show_id_episode or show_id_sXX_eYY
        import re
        # Extract show_id (everything before _s or last _)
        match = re.match(r'^([^_]+(?:_[^_]+)*?)(?:_s\d+_e\d+|_\d+)$', id)
        if match:
            show_id = match.group(1)
        else:
            # Fallback to old method
            show_id = id.rsplit('_', 1)[0]
        
        show = next((s for s in SHOWS if s["id"] == show_id), None)
        
        if not show:
            print(f"Show not found for ID: {show_id}")
            raise HTTPException(status_code=404, detail="Show not found")
            
        # Search for the episode in all seasons
        episode = None
        for season in show["seasons"]:
            episode = next((ep for ep in season["episodes"] if ep["id"] == id), None)
            if episode:
                break
                
        if not episode:
            print(f"Episode not found for ID: {id}")
            raise HTTPException(status_code=404, detail="Episode not found")
        
        # Only log when starting a new video (no range header)
        if not request.headers.get("range"):
            print(f"New stream started - Show: {show['title']}, Episode: {episode['title']}")
            
    except Exception as e:
        print(f"Error in stream_video: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
        
    path = episode["file"]
    if not os.path.exists(path):
        raise HTTPException(status_code=404)

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