import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from yt_dlp import YoutubeDL

app = FastAPI(
    title="Universal Media Extractor API",
    description="API to extract media data, images, and video metadata from social links using yt-dlp"
)

class ExtractRequest(BaseModel):
    url: str

@app.get("/")
def read_root():
    return {"status": "running", "message": "Social media extractor API is active."}

@app.post("/extract")
def extract_media(payload: ExtractRequest):
    url = payload.url
    if not url:
        raise HTTPException(status_code=400, detail="URL parameter is required.")

    # Configure yt-dlp to mimic a modern browser and extract full data
    ydl_opts = {
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Fetch-Mode': 'navigate',
        },
        'skip_download': True,        # Do not download files to Render storage
        'extract_flat': False,        # Fully evaluate playlists/galleries
        'dump_single_json': True,     # Gather raw response data mapping
        'no_warnings': True,
        'quiet': True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            # Extract full info dictionary
            info = ydl.extract_info(url, download=False)
            
            # Sanitize the info dict to make it safe for JSON serialization
            sanitized_info = ydl.sanitize_info(info)
            
            # 1. Collect all available image variations
            images = []
            if 'thumbnail' in sanitized_info and sanitized_info['thumbnail']:
                images.append(sanitized_info['thumbnail'])
            if 'thumbnails' in sanitized_info:
                for t in sanitized_info['thumbnails']:
                    if 'url' in t:
                        images.append(t['url'])
                        
            # Handle child entries for multi-image posts or carousels
            if 'entries' in sanitized_info:
                for entry in sanitized_info['entries']:
                    if entry and 'thumbnail' in entry:
                        images.append(entry['thumbnail'])
                    if entry and 'thumbnails' in entry:
                        images.extend([t['url'] for t in entry['thumbnails'] if 'url' in t])

            # Deduplicate image URLs
            images = list(dict.fromkeys(images))

            # 2. Extract requested key fields with robust fallbacks
            main_thumbnail = sanitized_info.get("thumbnail") or (images[0] if images else None)
            duration = sanitized_info.get("duration")  # Length of video in seconds (returns None for text/image posts)
            
            # Fallback chains for author details across various platforms
            author = (
                sanitized_info.get("uploader") or 
                sanitized_info.get("uploader_id") or 
                sanitized_info.get("channel") or 
                sanitized_info.get("author")
            )
            
            # Identity of the engine/platform processing the URL
            platform = sanitized_info.get("extractor_key") or sanitized_info.get("extractor")

            return {
                "success": True,
                "title": sanitized_info.get("title") or sanitized_info.get("description", "")[:50],
                "platform": platform,
                "author": author,
                "duration_seconds": duration,
                "thumbnail": main_thumbnail,
                "all_images": images,
                "raw_data": sanitized_info
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
