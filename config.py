"""
Configuration file for Video Streaming Backend

Edit these paths to match your system setup.
"""

# ============== Paths Configuration ==============

# Video files directory (where your shows/episodes are stored)
VIDEOS_PATH = "/home/tony-server/website/video-website/videos"

# Poster images directory
POSTERS_PATH = "posters"

# HLS streaming directory (generated files)
HLS_PATH = "hls"

# User data directory (database, watch progress, etc.)
DATA_PATH = "data"

# ============== Server Configuration ==============

# Server host (usually 127.0.0.1 for localhost)
SERVER_HOST = "127.0.0.1"

# Server port
SERVER_PORT = 8087

# JWT Secret Key (change this in production!)
SECRET_KEY = "your-secret-key-change-in-production"

# Token expiration time in minutes
TOKEN_EXPIRE_MINUTES = 43200  # 30 days
