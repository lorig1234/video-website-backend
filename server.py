# server.py
"""
Video Streaming Server

Main FastAPI application that orchestrates all routers and services.

Routers:
- /api/auth - Authentication (register, login, logout)
- /api/user - User data (watch progress, history, IPs)
- /api/shows - Shows and episodes catalog
- /api/stream - Video streaming
"""

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import logging
import re
from pathlib import Path

# Import configuration
import config

# Configure logging
logging.getLogger("uvicorn.error").setLevel(logging.INFO)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)
logging.getLogger("uvicorn.asgi").setLevel(logging.INFO)

# Create a custom filter to ignore connection reset errors
class IgnoreConnectionResetFilter(logging.Filter):
    def filter(self, record):
        return "ConnectionResetError" not in str(record.exc_info) if record.exc_info else True

asyncio_logger = logging.getLogger("asyncio")
asyncio_logger.addFilter(IgnoreConnectionResetFilter())

# Import routers
from routers import auth_router, user_router, shows_router, streaming_router, movies_router, claude_router, subtitle_router

# ============== App Configuration ==============

app = FastAPI(
    title="Video Streaming API",
    description="""
## 🎬 Video Streaming Backend API

A Netflix-style video streaming backend with user authentication and watch history tracking.

### Features:
- **Authentication**: Register, login, logout with JWT tokens
- **User Management**: Track watch history, continue watching, IP logging
- **Shows Catalog**: Browse shows and episodes
- **Video Streaming**: HTTP range request support for seeking

### Authentication:
Most user endpoints require authentication. To authenticate:
1. Register a new account at `/api/auth/register`
2. Login at `/api/auth/login` to get a token
3. Click the 🔒 **Authorize** button above
4. Enter your token as: `Bearer <your_token>`

### Quick Start:
1. **Register**: `POST /api/auth/register`
2. **Login**: `POST /api/auth/login` → Get token
3. **Browse Shows**: `GET /api/shows`
4. **Watch Video**: `GET /api/stream/{episode_id}`
5. **Save Progress**: `POST /api/user/watch-progress`
    """,
    version="1.0.0",
    contact={
        "name": "Video Streaming API"
    },
    license_info={
        "name": "MIT"
    },
    openapi_tags=[
        {
            "name": "Authentication",
            "description": "User registration, login, logout, and token management"
        },
        {
            "name": "User",
            "description": "User-specific data: watch progress, history, and security"
        },
        {
            "name": "Shows",
            "description": "Browse shows and get episode information"
        },
        {
            "name": "Streaming",
            "description": "Video streaming with range request support"
        }
    ]
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create necessary directories
os.makedirs(config.POSTERS_PATH, exist_ok=True)
os.makedirs(config.HLS_PATH, exist_ok=True)
os.makedirs(config.DATA_PATH, exist_ok=True)
# Note: videos directory is not created - it should already exist at the configured path


# ============== Video Directory Scanner ==============

def scan_video_directory():
    """Scan videos directory and generate show data"""
    shows = []
    videos_dir = Path(config.VIDEOS_PATH)
    
    if not videos_dir.exists():
        print(f"⚠️  Warning: Videos directory not found at: {config.VIDEOS_PATH}")
        print(f"   Please update VIDEOS_PATH in config.py to point to your videos folder")
        return []
    
    # Scan each show directory (skip "Movies" folder - handled separately)
    for show_dir in videos_dir.iterdir():
        if show_dir.is_dir() and not show_dir.name.startswith('.') and show_dir.name.lower() != 'movies':
            show_name = show_dir.name.replace('_', ' ').title()
            show_id = show_dir.name.lower()
            
            # Get all episodes for this show
            total_episodes = []
            season_episodes = {}
            
            # Look for season folders
            season_folders = sorted([
                f for f in show_dir.iterdir() 
                if f.is_dir() and (
                    re.match(r'S\d+', f.name, re.IGNORECASE) or 
                    re.match(r'.*season\s*\d+', f.name, re.IGNORECASE)
                )
            ])
            
            if season_folders:
                # Process season-based structure
                for season_folder in season_folders:
                    if re.match(r'S\d+', season_folder.name, re.IGNORECASE):
                        season_number = season_folder.name.upper()
                    else:
                        match = re.search(r'season\s*(\d+)', season_folder.name, re.IGNORECASE)
                        if match:
                            season_num = int(match.group(1))
                            season_number = f"S{season_num:02d}"
                        else:
                            season_number = season_folder.name.upper()
                    
                    if season_number not in season_episodes:
                        season_episodes[season_number] = []
                    
                    # Find video files with priority
                    safari_files = list(season_folder.glob("*.safari.mp4"))
                    h264_files = list(season_folder.glob("*.h264.mp4"))
                    mp4_files = [f for f in season_folder.glob("*.mp4") 
                                if not f.name.endswith('.h264.mp4') 
                                and not f.name.endswith('.safari.mp4')]
                    mkv_files = list(season_folder.glob("*.mkv"))
                    avi_files = list(season_folder.glob("*.avi"))
                    
                    all_videos = {}
                    for f in mkv_files + avi_files + mp4_files + h264_files + safari_files:
                        base_name = f.stem.replace('.h264', '').replace('.safari', '')
                        ep_match = re.search(r'[Ss]\d+[Ee]\d+', f.name)
                        if ep_match:
                            key = ep_match.group(0)
                        else:
                            key = base_name
                        
                        if key not in all_videos:
                            all_videos[key] = f
                        elif f.name.endswith('.safari.mp4'):
                            all_videos[key] = f
                        elif f.name.endswith('.h264.mp4') and not all_videos[key].name.endswith('.safari.mp4'):
                            all_videos[key] = f
                        elif f.suffix == '.mp4' and all_videos[key].suffix in ['.mkv', '.avi']:
                            all_videos[key] = f
                    
                    video_files = sorted(all_videos.values(), key=lambda x: x.name)
                    
                    for video_file in video_files:
                        episode_number = len(total_episodes) + 1
                        filename = video_file.stem
                        episode_match = re.search(r'[Ss]\d+[Ee](\d+)', filename)
                        episode_num_in_season = int(episode_match.group(1)) if episode_match else len(season_episodes[season_number]) + 1
                        
                        title = filename
                        title = re.sub(rf'^{re.escape(show_name)}\.?', '', title, flags=re.IGNORECASE)
                        title = re.sub(r'[Ss]\d+[Ee]\d+\.?', '', title)
                        title = re.sub(r'\d+p.*$', '', title)
                        title = re.sub(r'(BluRay|WEB-DL|HDTV|x264|x265|HEVC|PSA).*$', '', title, flags=re.IGNORECASE)
                        title = title.replace('.', ' ').replace('_', ' ')
                        title = ' '.join(title.split()).strip()
                        
                        if not title:
                            title = f"Episode {episode_num_in_season}"
                        
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
                # Process flat structure
                video_files = sorted(
                    list(show_dir.glob("*.mp4")) + 
                    list(show_dir.glob("*.mkv")) + 
                    list(show_dir.glob("*.avi"))
                )
                
                for video_file in video_files:
                    episode_number = len(total_episodes) + 1
                    title = video_file.stem.replace('_', ' ').replace('.', ' ')
                    if title.lower().startswith(show_name.lower()):
                        title = title[len(show_name):].strip()
                    
                    date_match = re.search(r'20\d{2}', title)
                    season_year = date_match.group(0) if date_match else "Other"
                    
                    if season_year not in season_episodes:
                        season_episodes[season_year] = []
                    
                    episode = {
                        "id": f"{show_id}_{episode_number}",
                        "title": title,
                        "number": len(season_episodes[season_year]) + 1,
                        "season": season_year,
                        "file": str(video_file)
                    }
                    
                    season_episodes[season_year].append(episode)
                    total_episodes.append(episode)
            
            if total_episodes:
                sorted_seasons = sorted(season_episodes.keys())
                
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
                print(f"✓ Added show: {show_name} ({len(total_episodes)} episodes, {len(seasons)} seasons)")
    
    return shows


# ============== Movies Directory Scanner ==============

def scan_movies_directory():
    """Scan the Movies subdirectory and generate movie data"""
    movies = []
    movies_dir = Path(config.VIDEOS_PATH) / "Movies"
    
    if not movies_dir.exists():
        print(f"ℹ️  No Movies directory found at: {movies_dir}")
        return []
    
    for movie_folder in sorted(movies_dir.iterdir()):
        if not movie_folder.is_dir() or movie_folder.name.startswith('.'):
            continue
        
        # Find the first video file inside the folder
        video_file = None
        for ext in ('*.mp4', '*.mkv', '*.avi'):
            found = list(movie_folder.glob(ext))
            if found:
                video_file = found[0]
                break
        
        if not video_file:
            continue
        
        folder_name = movie_folder.name
        
        # Try to extract title and year from folder name
        # Patterns: "Title (Year) [quality]", "Title.Year.quality..."
        year = None
        title = folder_name
        
        # Pattern 1: "Title (Year) [extras]"
        m = re.match(r'^(.+?)\s*\((\d{4})\)', folder_name)
        if m:
            title = m.group(1).strip()
            year = int(m.group(2))
        else:
            # Pattern 2: "Title.Year.quality..."
            m = re.search(r'^(.+?)[.\s](\d{4})[.\s]', folder_name)
            if m:
                title = m.group(1).replace('.', ' ').strip()
                year = int(m.group(2))
            else:
                title = folder_name.replace('.', ' ').replace('_', ' ').strip()
        
        # Clean up title
        title = re.sub(r'\[.*?\]', '', title).strip()
        title = re.sub(r'(1080p|720p|480p|BluRay|BRRip|WEB-DL|HDTV|x264|x265|HEVC|YIFY|LAMA|TGx|AAC).*$', '', title, flags=re.IGNORECASE).strip()
        title = title.rstrip('.-_ ')
        
        movie_id = re.sub(r'[^a-z0-9]+', '_', folder_name.lower()).strip('_')
        
        # Find poster image in the movie folder (jpg/jpeg)
        poster_file = None
        for pat in ('*.jpeg', '*.jpg'):
            found = list(movie_folder.glob(pat))
            if found:
                poster_file = str(found[0])
                break
        
        movie = {
            "id": movie_id,
            "title": title,
            "year": year,
            "file": str(video_file),
            "poster_file": poster_file,
            "poster": f"/api/movies/poster/{movie_id}" if poster_file else f"/posters/{movie_id}.jpg"
        }
        movies.append(movie)
        year_str = f" ({year})" if year else ""
        print(f"✓ Added movie: {title}{year_str}")
    
    return movies


# ============== Initialize Data ==============

print("\n🎬 Scanning video directory...")
SHOWS = scan_video_directory()
print(f"📺 Found {len(SHOWS)} shows\n")

print("🎥 Scanning movies directory...")
MOVIES = scan_movies_directory()
print(f"🎥 Found {len(MOVIES)} movies\n")

# Share shows data with routers
shows_router.set_shows(SHOWS)
streaming_router.set_shows(SHOWS)
movies_router.set_movies(MOVIES)
subtitle_router.set_movies(MOVIES)


# ============== Register Routers ==============

app.include_router(auth_router.router)
app.include_router(user_router.router)
app.include_router(shows_router.router)
app.include_router(streaming_router.router)
app.include_router(movies_router.router)
app.include_router(claude_router.router)
app.include_router(subtitle_router.router)


# ============== Static Files ==============

app.mount("/posters", StaticFiles(directory=config.POSTERS_PATH), name="posters")
app.mount("/hls", StaticFiles(directory=config.HLS_PATH), name="hls")


# ============== Frontend Routes ==============

@app.get("/", include_in_schema=False)
async def get_index():
    """Serve frontend index page"""
    return FileResponse("../video-website-frontend/index.html")


@app.get("/player.html", include_in_schema=False)
async def get_player_html():
    """Serve frontend player page"""
    return FileResponse("../video-website-frontend/player.html")


@app.get("/player", include_in_schema=False)
async def get_player():
    """Serve frontend player page (alternative route)"""
    return FileResponse("../video-website-frontend/player.html")


@app.get("/config.js", include_in_schema=False)
async def get_config():
    """Serve frontend config"""
    return FileResponse("../video-website-frontend/config.js")


# ============== Entry Point ==============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.SERVER_HOST, port=config.SERVER_PORT)
