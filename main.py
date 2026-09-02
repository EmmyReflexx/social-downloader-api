import os
import shutil
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

app = FastAPI(title="Social Media Direct Video Extractor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared User-Agent string to prevent blocks
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'

# --- FIXED: Dedicated app-level directory to ensure reliable Render write permissions ---
DOWNLOAD_DIR = os.path.abspath("./downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def remove_file(path: str):
    """Background task to delete the temporary file after it is sent to the user."""
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

@app.get("/")
def home():
    return {
        "message": "Extractor API is online.",
        "endpoints": {
            "metadata_extraction": "/extract?url=YOUR_URL",
            "physical_download": "/download?url=YOUR_URL"
        }
    }

@app.get("/download")
def download_video(
    background_tasks: BackgroundTasks,
    url: str = Query(..., description="The social media video URL to download directly")
):
    """
    Downloads the video to the server disk and streams it directly to the client.
    Triggers an automatic file download pop-up in the browser.
    """
    # Use our stable application-level directory path template
    output_template = os.path.join(DOWNLOAD_DIR, 'dl_%(id)s.%(ext)s')

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'best',
        'outtmpl': output_template,
        'http_headers': {
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,video/webm,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Force the server to pull the full file down locally
            info = ydl.extract_info(url, download=True)
            
            # --- FIXED: Dynamically capture the actual filename extension ytdl chose ---
            filename = ydl.prepare_filename(info)
            actual_ext = os.path.splitext(filename)[1] or ".mp4"
            
            if not os.path.exists(filename):
                raise HTTPException(status_code=500, detail="Downloaded file was not found on disk.")

            # Queue cleanup so Render storage doesn't hit container memory limits
            background_tasks.add_task(remove_file, filename)

            # Generate a clean, matching extension name for the browser download bar
            download_name = f"{info.get('id', 'video')}{actual_ext}"

            return FileResponse(
                path=filename, 
                media_type='application/octet-stream', # Forces a raw binary attachment download popup
                filename=download_name
            )

    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"yt-dlp Download Error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/extract")
def extract_metadata(url: str = Query(..., description="The social media video URL to extract info from")):
    """
    Extracts stream URLs and structural metadata without downloading the file itself.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'best',
        'http_headers': {
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,video/webm,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise HTTPException(status_code=404, detail="Could not extract metadata from this URL.")

            formats = info.get("formats", [])
            
            response_data = {
                "title": info.get("title") or info.get("description", "")[:50] or "Social Media Video",
                "author": info.get("uploader") or info.get("channel") or "Unknown",
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "video_link": None,
                "audio_link": None,
                "images": False # Preserving your custom structural requirements
            }

            video_link = None
            audio_link = None

            # 1. Prioritize combined video + audio streams
            for f in formats:
                if f.get("vcodec") != "none" and f.get("acodec") != "none" and f.get("url"):
                    video_link = f.get("url")
                    break

            # 2. Fallback to video-only track
            if not video_link:
                video_formats = [f for f in formats if f.get("vcodec") != "none" and f.get("url")]
                if video_formats:
                    video_link = video_formats[-1].get("url")

            # 3. Look for standalone audio stream
            for f in formats:
                if f.get("vcodec") == "none" and f.get("acodec") != "none" and f.get("url"):
                    audio_link = f.get("url")
                    break

            if not video_link:
                video_link = info.get("url")

            response_data["video_link"] = video_link
            response_data["audio_link"] = audio_link or video_link
            
            return response_data

    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"yt-dlp Extraction Error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
