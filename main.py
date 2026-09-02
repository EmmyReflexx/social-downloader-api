import os
import re
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

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'

DOWNLOAD_DIR = os.path.abspath("./downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def remove_file(path: str):
    """Background task to delete the temporary file after it is sent to the user."""
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

def sanitize_filename(name: str) -> str:
    """Removes special characters, spaces, and emojis to ensure a safe file system path."""
    if not name:
        return "video"
    clean = re.sub(r'[^a-zA-Z0-9\s\-_]', '', name)
    clean = re.sub(r'\s+', '_', clean).strip('_')
    return clean[:50]

@app.get("/")
def home():
    return {
        "message": "Extractor API is online.",
        "endpoints": {
            "metadata_extraction": "/extract?url=YOUR_URL",
            "physical_download": "/download?url=YOUR_URL&quality=best"
        }
    }

@app.get("/download")
def download_video(
    background_tasks: BackgroundTasks,
    url: str = Query(..., description="The social media video URL to download directly"),
    quality: str = Query("best", description="Choose the video quality: 'best' or 'worst'")
):
    """
    Downloads the video in either best or worst resolution quality and serves it 
    named after the title as an instant browser attachment file.
    """
    # 1. Map the request query input to the correct yt-dlp format parameter string
    quality = quality.lower().strip()
    if quality == "worst":
        format_selector = "worstvideo+worstaudio/worst"
    else:
        format_selector = "best" # Fallback to best if unspecified

    # 2. Fetch metadata first to grab the title for the filename
    pre_opts = {
        'quiet': True,
        'no_warnings': True,
        'http_headers': {'User-Agent': USER_AGENT}
    }
    
    try:
        with yt_dlp.YoutubeDL(pre_opts) as ydl_pre:
            meta = ydl_pre.extract_info(url, download=False)
            video_title = meta.get("title") or meta.get("description", "")[:30] or "social_video"
            safe_title = sanitize_filename(video_title)
    except Exception:
        safe_title = "social_video"

    # Set up our output path layout using the clean title template
    output_template = os.path.join(DOWNLOAD_DIR, f'{safe_title}_%(id)s.%(ext)s')

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': format_selector, # --- FIXED: Maps dynamically to user request ---
        'outtmpl': output_template,
        'http_headers': {
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,video/webm,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # Extract actual container file extension ytdl saved (e.g. .mp4, .webm)
            _, actual_ext = os.path.splitext(filename)
            actual_ext = actual_ext or ".mp4"
            
            if not os.path.exists(filename):
                raise HTTPException(status_code=500, detail="Downloaded file was not found on disk.")

            # Queue cleanup background task
            background_tasks.add_task(remove_file, filename)

            # Assemble the download name with the user title and actual path extension
            download_name = f"{safe_title}{actual_ext}"

            return FileResponse(
                path=filename, 
                media_type='application/octet-stream', 
                filename=download_name
            )

    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"yt-dlp Download Error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/extract")
def extract_metadata(url: str = Query(..., description="The social media video URL to extract info from")):
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
            
            # Identify sizing info from formats array safely
            valid_sizes = [f.get("filesize") or f.get("filesize_approx") for f in formats if (f.get("filesize") or f.get("filesize_approx"))]
            best_size = max(valid_sizes) if valid_sizes else None
            worst_size = min(valid_sizes) if valid_sizes else None

            response_data = {
                "title": info.get("title") or info.get("description", "")[:50] or "Social Media Video",
                "author": info.get("uploader") or info.get("channel") or "Unknown",
                "platform": info.get("extractor_key") or "Unknown",
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "best_filesize_bytes": best_size,
                "worst_filesize_bytes": worst_size,
                "video_link": None,
                "audio_link": None,
                "images": False
            }

            video_link = None
            audio_link = None

            for f in formats:
                if f.get("vcodec") != "none" and f.get("acodec") != "none" and f.get("url"):
                    video_link = f.get("url")
                    break

            if not video_link:
                video_formats = [f for f in formats if f.get("vcodec") != "none" and f.get("url")]
                if video_formats:
                    video_link = video_formats[-1].get("url")

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
