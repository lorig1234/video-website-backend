# Video Streaming Website - Backend

FastAPI backend for video streaming with show and season organization.

## Features

- 🎥 Video streaming with chunked HTTP responses
- 📂 Automatic season detection from filenames
- 🔄 Range request support for video seeking
- 🚀 Fast and efficient with FastAPI
- 📊 Show and episode organization

## Setup

### Prerequisites

- Python 3.8+
- pip

### Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create required directories:
```bash
mkdir videos posters hls
```

3. Add your video files under the `videos` directory in this structure:
```
videos/
  show_name/
    video1.mp4
    video2.mp4
    ...
```

### Running the Server

**Development:**
```bash
uvicorn server:app --host 0.0.0.0 --port 8085 --reload
```

**Production:**
```bash
uvicorn server:app --host 0.0.0.0 --port 8085 --workers 4
```

## API Endpoints

### Get All Shows
```
GET /api/shows
```
Returns list of all shows with episode counts.

### Get Show Details
```
GET /api/shows/{show_id}
```
Returns show details including all seasons and episodes.

### Stream Video
```
GET /api/stream/{episode_id}
```
Streams video with range request support.

## Configuration

### Video Organization

Videos are organized by show folders. The system automatically:
- Detects seasons based on year in filenames
- Generates episode numbers
- Creates show IDs from folder names

Example structure:
```
videos/
  league_of_legends/
    League of Legends 2019.04.18.mp4  -> Season 2019, Episode 1
    League of Legends 2020.01.05.mp4  -> Season 2020, Episode 1
  fortnite/
    Fortnite 2021.06.15.mp4           -> Season 2021, Episode 1
```

### CORS Configuration

The backend is configured to allow all origins for development.
For production, update the CORS settings in `server.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend-url.com"],  # Update this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Deployment

### Railway
1. Create a new project
2. Connect your repository
3. Add environment variables if needed
4. Deploy

### Heroku
1. Create a `Procfile`:
```
web: uvicorn server:app --host 0.0.0.0 --port $PORT
```
2. Push to Heroku

### DigitalOcean/AWS/GCP
Use uvicorn with gunicorn for production:
```bash
pip install gunicorn
gunicorn server:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8085
```

## Environment Variables

- `PORT`: Server port (default: 8085)
- `VIDEOS_DIR`: Path to videos directory (default: ./videos)

## Project Structure

```
video-website-backend/
├── server.py           # FastAPI application
├── requirements.txt    # Python dependencies
├── .gitignore         # Git ignore rules
├── README.md          # This file
└── videos/            # Video files (not in git)
```

## Frontend Repository

The frontend is in a separate repository:
- Repository: [video-website-frontend](../video-website-frontend)

## License

MIT
