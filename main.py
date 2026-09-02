import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

app = FastAPI(title="Social Media Media Extractor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "Extractor API is running. Use /download or /extract with ?url=YOUR_URL"}

@app.get("/download")
@app.get("/extract")
def extract_media(url: str = Query(..., description="The social media URL to extract")):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,  # Prevents crashing on image posts
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Fetch-Mode': 'navigate',
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise HTTPException(status_code=404, detail="Could not extract metadata from this URL.")

            # Base metadata payload
            response_data = {
                "title": info.get("title") or info.get("description", "")[:50] or "Social Media Post",
                "author": info.get("uploader") or info.get("channel") or "Unknown",
                "thumbnail": info.get("thumbnail"),
            }

            formats = info.get("formats", [])
            entries = info.get("entries") or info.get("requested_downloads")

            # --- CASE 1: MULTI-IMAGE POSTS / CAROUSELS ---
            # If there are sub-entries and they explicitly look like static image items
            if entries and any(item.get('ext') in ['jpg', 'png', 'webp'] or 'image' in item.get('format_id', '') for item in entries if item):
                image_links = []
                for entry in entries:
                    if entry:
                        img_url = entry.get("url") or entry.get("thumbnail")
                        if img_url:
                            image_links.append(img_url)
                
                if image_links:
                    response_data["images"] = image_links
                    return response_data

            # --- CASE 2: VIDEO EXTRACTOR FIXED BLOCK ---
            # If formats list exists, we have an actual playable video track
            if formats:
                video_link = None
                audio_link = None

                # Look for a combined format (contains both video and audio) first for ease of streaming
                for f in formats:
                    if f.get("vcodec") != "none" and f.get("acodec") != "none" and f.get("url"):
                        video_link = f.get("url")
                        break

                # If no combined format found, pick the highest quality standalone video format
                if not video_link:
                    video_formats = [f for f in formats if f.get("vcodec") != "none" and f.get("url")]
                    if video_formats:
                        # Sort by resolution/quality if available, otherwise take the last one
                        video_link = video_formats[-1].get("url")

                # Isolate a standalone audio stream if present
                for f in formats:
                    if f.get("vcodec") == "none" and f.get("acodec") != "none" and f.get("url"):
                        audio_link = f.get("url")
                        break

                # Root fallback if our loops couldn't match a format but yt-dlp dropped a direct root url
                if not video_link:
                    root_url = info.get("url")
                    if root_url and not any(ext in root_url for ext in [".jpg", ".png", ".webp"]):
                        video_link = root_url

                # If we successfully caught a video link, assemble the video dictionary response
                if video_link:
                    response_data["video_link"] = video_link
                    response_data["audio_link"] = audio_link or video_link  # Fallback to video track if audio stream doesn't split
                    return response_data

            # --- CASE 3: STATIC SINGLE IMAGE FALLBACK ---
            # Run this block if it has no video formats available 
            thumbnails = info.get("thumbnails", [])
            image_links = []
            
            if thumbnails:
                image_links = [t.get("url") for t in thumbnails if t.get("url")]
            
            if not image_links and info.get("thumbnail"):
                image_links.append(info.get("thumbnail"))
                
            if not image_links and info.get("url"):
                image_links.append(info.get("url"))

            response_data["images"] = image_links
            return response_data

    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"yt-dlp Extraction Error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server Processing Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
