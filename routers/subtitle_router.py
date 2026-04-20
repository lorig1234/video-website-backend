# routers/subtitle_router.py
"""
Subtitle API Router

Whisper-based subtitle generation and serving for movies.

Endpoints:
  POST /api/subtitles/generate/{movie_id}    Start generation for one movie
  POST /api/subtitles/generate-all           Queue generation for all movies
  GET  /api/subtitles/status                 Status for all movies
  GET  /api/subtitles/status/{movie_id}      Status for one movie
  GET  /api/subtitles/file/{movie_id}/{lang} Serve .vtt subtitle file
  GET  /api/subtitles/{movie_id}             List available subtitle tracks
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, FileResponse
import os
import threading
import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/subtitles", tags=["Subtitles"])

MOVIES: list = []
JOBS: dict = {}             # movie_id -> {status, ...}
_LOCK = threading.Lock()
_WHISPER_SEM = threading.Semaphore(1)   # one transcription at a time

JOBS_FILE = "data/subtitle_jobs.json"
WHISPER_MODEL = "small"


# ── helpers ────────────────────────────────────────────────────────────────

def set_movies(movies_data: list):
    global MOVIES
    MOVIES = movies_data


def _load_jobs():
    global JOBS
    if os.path.exists(JOBS_FILE):
        try:
            with open(JOBS_FILE) as f:
                JOBS = json.load(f)
        except Exception:
            JOBS = {}


def _save_jobs():
    os.makedirs("data", exist_ok=True)
    with open(JOBS_FILE, "w") as f:
        json.dump(JOBS, f, indent=2)


def _vtt_path(movie: dict, lang: str = "en") -> str:
    stem = Path(movie["file"]).stem
    folder = os.path.dirname(movie["file"])
    return os.path.join(folder, f"{stem}.{lang}.vtt")


def _get_duration(video_path: str) -> float | None:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=30,
        )
        return float(r.stdout.strip())
    except Exception:
        return None


def _calc_progress(job: dict) -> int | None:
    """Estimate percent complete for a running job based on elapsed time vs duration."""
    if job.get("status") != "running":
        return None
    duration = job.get("duration_seconds")
    started_at = job.get("started_at")
    # Fall back to file if in-memory job is missing duration (e.g. from a previous run)
    if not duration and os.path.exists(JOBS_FILE):
        try:
            with open(JOBS_FILE) as f:
                file_jobs = json.load(f)
            for mid, fjob in file_jobs.items():
                if fjob.get("started_at") == started_at:
                    duration = fjob.get("duration_seconds")
                    break
        except Exception:
            pass
    if not duration or not started_at:
        return None
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        pct = int(min(99, elapsed / duration * 100))
        return pct
    except Exception:
        return None


def _glob_escape(s: str) -> str:
    return s.replace("[", "[[]").replace("?", "[?]").replace("*", "[*]")


def _list_tracks(movie: dict) -> list:
    stem = Path(movie["file"]).stem
    folder = Path(os.path.dirname(movie["file"]))
    tracks = []
    for vtt in sorted(folder.glob(f"{_glob_escape(stem)}.*.vtt")):
        lang = vtt.stem.rsplit(".", 1)[-1]
        tracks.append({
            "language": lang,
            "url": f"/api/subtitles/file/{movie['id']}/{lang}",
        })
    return tracks


def _fmt_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _write_vtt(segments: list, path: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        idx = 1
        for seg in segments:
            text = seg["text"].strip()
            if not text:
                continue
            f.write(f"{idx}\n{_fmt_ts(seg['start'])} --> {_fmt_ts(seg['end'])}\n{text}\n\n")
            idx += 1


# ── background worker ──────────────────────────────────────────────────────

def _run_whisper(movie_id: str, video_path: str, vtt_path: str):
    """Run in a daemon thread; acquires _WHISPER_SEM so only one runs at a time."""
    with _WHISPER_SEM:
        duration = _get_duration(video_path)
        with _LOCK:
            entry = JOBS.get(movie_id, {})
            JOBS[movie_id] = {
                "status": "running",
                "queued_at": entry.get("queued_at"),
                "started_at": datetime.now(timezone.utc).isoformat(),
                **({"duration_seconds": duration} if duration else {}),
            }
            _save_jobs()

        try:
            import whisper
            logger.info(f"[Whisper] loading model '{WHISPER_MODEL}'")
            model = whisper.load_model(WHISPER_MODEL)
            logger.info(f"[Whisper] transcribing: {video_path}")
            result = model.transcribe(video_path, verbose=False, language="en")
            _write_vtt(result["segments"], vtt_path)

            with _LOCK:
                JOBS[movie_id] = {
                    "status": "done",
                    "queued_at": JOBS[movie_id].get("queued_at"),
                    "started_at": JOBS[movie_id].get("started_at"),
                    "finished_at": datetime.utcnow().isoformat(),
                }
                _save_jobs()
            logger.info(f"[Whisper] done: {movie_id}")

        except Exception as exc:
            logger.error(f"[Whisper] failed for {movie_id}: {exc}")
            with _LOCK:
                JOBS[movie_id] = {
                    "status": "failed",
                    "error": str(exc),
                    "failed_at": datetime.utcnow().isoformat(),
                }
                _save_jobs()


def _enqueue(movie_id: str, video_path: str, vtt_path: str):
    """Mark as queued (inside caller's lock) then start daemon thread."""
    t = threading.Thread(
        target=_run_whisper,
        args=(movie_id, video_path, vtt_path),
        daemon=True,
        name=f"whisper-{movie_id}",
    )
    t.start()


# ── endpoints ──────────────────────────────────────────────────────────────

@router.post(
    "/generate/{movie_id}",
    summary="Generate subtitles for one movie",
    description="Starts Whisper AI transcription in background. Poll `/status/{movie_id}` to track progress.",
)
def generate_subtitles(movie_id: str):
    movie = next((m for m in MOVIES if m["id"] == movie_id), None)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    path = _vtt_path(movie)

    with _LOCK:
        job = JOBS.get(movie_id, {})
        if job.get("status") in ("queued", "running"):
            return JSONResponse({"status": job["status"], "message": "Already in progress"})
        if os.path.exists(path) and job.get("status") != "failed":
            return JSONResponse({"status": "done", "message": "Subtitles already exist"})
        # Set queued state atomically before releasing lock (prevents duplicate starts)
        JOBS[movie_id] = {"status": "queued", "queued_at": datetime.utcnow().isoformat()}
        _save_jobs()

    _enqueue(movie_id, movie["file"], path)
    return JSONResponse({
        "status": "started",
        "message": f"Subtitle generation started for '{movie['title']}'",
    })


@router.post(
    "/generate-all",
    summary="Generate subtitles for every movie",
    description="Queues Whisper transcription for all movies missing subtitles. Jobs run one at a time.",
)
def generate_all_subtitles():
    started, skipped = [], []

    for movie in MOVIES:
        mid = movie["id"]
        path = _vtt_path(movie)

        with _LOCK:
            job = JOBS.get(mid, {})
            if job.get("status") in ("queued", "running"):
                skipped.append({"id": mid, "title": movie["title"], "reason": "already_running"})
                continue
            if os.path.exists(path) and job.get("status") != "failed":
                skipped.append({"id": mid, "title": movie["title"], "reason": "already_exists"})
                continue
            JOBS[mid] = {"status": "queued", "queued_at": datetime.utcnow().isoformat()}
            _save_jobs()

        _enqueue(mid, movie["file"], path)
        started.append({"id": mid, "title": movie["title"]})

    return JSONResponse({
        "started": started,
        "skipped": skipped,
        "total_started": len(started),
        "total_skipped": len(skipped),
    })


@router.get(
    "/status",
    summary="Get subtitle status for all movies",
)
def get_all_statuses():
    results = []
    for movie in MOVIES:
        mid = movie["id"]
        tracks = _list_tracks(movie)
        if tracks:
            results.append({
                "movie_id": mid, "title": movie["title"],
                "status": "done", "subtitles": tracks,
            })
        else:
            job = JOBS.get(mid, {})
            progress = _calc_progress(job)
            results.append({
                "movie_id": mid, "title": movie["title"],
                "status": job.get("status", "none"),
                **{k: v for k, v in job.items() if k != "status"},
                **({"progress_percent": progress} if progress is not None else {}),
            })
    return JSONResponse(results)


@router.get(
    "/status/{movie_id}",
    summary="Get subtitle status for one movie",
)
def get_subtitle_status(movie_id: str):
    movie = next((m for m in MOVIES if m["id"] == movie_id), None)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    tracks = _list_tracks(movie)
    if tracks:
        return JSONResponse({
            "movie_id": movie_id, "title": movie["title"],
            "status": "done", "subtitles": tracks,
        })

    job = JOBS.get(movie_id)
    if job:
        progress = _calc_progress(job)
        return JSONResponse({
            "movie_id": movie_id, "title": movie["title"], **job,
            **({"progress_percent": progress} if progress is not None else {}),
        })

    return JSONResponse({"movie_id": movie_id, "title": movie["title"], "status": "none"})


@router.get(
    "/file/{movie_id}/{lang}",
    summary="Serve a subtitle file",
    description="Returns the WebVTT file. `lang` is the language code returned by the status/list endpoints (e.g. `en`).",
)
def serve_subtitle_file(movie_id: str, lang: str):
    movie = next((m for m in MOVIES if m["id"] == movie_id), None)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    path = _vtt_path(movie, lang)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"No '{lang}' subtitle found for this movie")

    return FileResponse(
        path,
        media_type="text/vtt",
        headers={"Access-Control-Allow-Origin": "*"},
    )


@router.get(
    "/{movie_id}",
    summary="List available subtitle tracks",
    description="Returns all generated subtitle languages for a movie.",
)
def list_subtitles(movie_id: str):
    movie = next((m for m in MOVIES if m["id"] == movie_id), None)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    return JSONResponse({
        "movie_id": movie_id,
        "title": movie["title"],
        "subtitles": _list_tracks(movie),
    })


# ── load persisted job state on startup ───────────────────────────────────
_load_jobs()
