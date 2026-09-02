import os
import subprocess
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

app = FastAPI(title="Social Media Unified API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared browser identity string to bypass basic automation firewalls
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'

def extract_images_via_gallery_dl(url: str) -> list:
    """
    Calls the system gallery-dl binary while explicitly injecting a valid 
    browser user-agent to bypass platform access blocks.
    """
    try:
        # -g outputs clean raw links line-by-line
        # --http-user-agent tricks Instagram into thinking gallery-dl is a real chrome browser
        cmd = [
            "gallery-dl", 
            "-g", 
            "--ignore-errors", 
            "--http-user-agent", USER_AGENT,
            url
        ]
        
        result = subprocess.run(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True, 
            timeout=30
        )
        
        if result.stdout:
            links = [line.strip() for line in result.stdout.split('\n') if line.strip().startswith("http")]
            return links
        return []
    except Exception:
        return []

@app.get("/")
def home():
    return {"message": "API is online. Use /download or /extract with ?url=YOUR_URL"}

@app.get("/download")
@app.get("/extract")
def extract_media(url: str = Query(..., description="The social media URL to extract")):
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'http_headers': {
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Fetch-Mode': 'navigate',
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise Exception("Empty metadata returned by yt-dlp.")

            response_data = {
                "title": info.get("title") or info.get("description", "")[:50] or "Social Media Post",
                "author": info.get("uploader") or info.get("channel") or "Unknown",
                "thumbnail": info.get("thumbnail"),
            }

            # If it's explicitly identified as an image container by lack of formats
            if info.get('ext') in ['jpg', 'png', 'webp'] or not info.get('formats'):
                raise yt_dlp.utils.DownloadError("Detected image post format.")

            # Isolate video streams
            formats = info.get("formats", [])
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

            if video_link:
                response_data["video_link"] = video_link
                response_data["audio_link"] = audio_link or video_link
                response_data["images"] = False  # Keep your fixed JSON structure
                return response_data
            else:
                raise yt_dlp.utils.DownloadError("No streaming video container found.")

    except (yt_dlp.utils.DownloadError, Exception) as e:
        # ----------------------------------------------------
        # FALLBACK ENGINE: FIRES AUTOMATICALLY FOR IMAGES
        # ----------------------------------------------------
        fallback_title = "Social Media Image Post"
        fallback_author = "Unknown"
        fallback_thumb = None
        
        # Pull soft metadata parameters flatly using the valid browser user agent
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True, 'ignoreerrors': True, 'http_headers': {'User-Agent': USER_AGENT}}) as ydl_flat:
                f_info = ydl_flat.extract_info(url, download=False)
                if f_info:
                    fallback_title = f_info.get("title") or f_info.get("description", "")[:50] or fallback_title
                    fallback_author = f_info.get("uploader") or f_info.get("channel") or fallback_author
                    fallback_thumb = f_info.get("thumbnail")
        except Exception:
            pass

        # Extract with the upgraded header-injected gallery-dl function
        images = extract_images_via_gallery_dl(url)

        if images:
            return {
                "title": fallback_title,
                "author": fallback_author,
                "thumbnail": fallback_thumb or images[0],
                "video_link": None,
                "audio_link": None,
                "images": images
            }
        
        # Final emergency array mapping if gallery-dl still returns nothing
        if fallback_thumb:
            return {
                "title": fallback_title,
                "author": fallback_author,
                "thumbnail": fallback_thumb,
                "video_link": None,
                "audio_link": None,
                "images": [fallback_thumb]
            }

        raise HTTPException(status_code=400, detail=f"Extraction failed on both engines. Trace: {str(e)}")
