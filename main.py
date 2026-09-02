import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

app = FastAPI(title="Social Media Media Extractor API")

# Enable CORS so you can call this API from your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "Extractor API is running. Use /extract?url=YOUR_URL"}

@app.get("/extract")
def extract_media(url: str = Query(..., description="The social media URL to extract")):
    # Configure yt-dlp to mimic a real desktop browser
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Fetch-Mode': 'navigate',
        },
        'extract_flat': False,  # Ensure it expands playlists/multi-images if supported
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise HTTPException(status_code=404, detail="Could not extract metadata.")

            # Base metadata
            response_data = {
                "title": info.get("title") or info.get("description", "")[:50],
                "author": info.get("uploader") or info.get("channel", "Unknown"),
                "thumbnail": info.get("thumbnail"),
            }

            # Check for multiple entries (Image galleries, carousels, or playlists)
            entries = info.get("entries") or info.get("requested_downloads")
            
            # 1. Handle Multi-Image Posts / Galleries
            if entries and any(item.get('ext') in ['jpg', 'png', 'webp'] or 'image' in item.get('format_id', '') for item in entries if item):
                image_links = []
                for entry in entries:
                    if entry:
                        # Fallback cascade to grab the direct URL
                        img_url = entry.get("url") or entry.get("thumbnail")
                        if img_url:
                            image_links.append(img_url)
                
                response_data["images"] = image_links
                return response_data

            # 2. Handle Single Image Fallback (e.g., if a post returns an image format directly)
            elif info.get('ext') in ['jpg', 'png', 'webp']:
                response_data["images"] = [info.get("url")]
                return response_data

            # 3. Handle Video Posts (Return video, audio, and thumbnail)
            else:
                # Find best video link
                response_data["video_link"] = info.get("url")
                
                # Try to isolate pure audio link if separate formats exist
                audio_link = None
                formats = info.get("formats", [])
                for f in formats:
                    if f.get("vcodec") == "none" and f.get("acodec") != "none":
                        audio_link = f.get("url")
                        break
                
                response_data["audio_link"] = audio_link or info.get("url") # Fallback to combined video/audio url
                return response_data

    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"yt-dlp Error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    # Render sets the PORT dynamically via environment variables
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
