import os
from fastapi import FastAPI, HTTPException, Query
from yt_dlp import YoutubeDL

app = FastAPI(
    title="Social Media Media Extractor API",
    description="Clean API separating responses strictly between image assets and video links"
)

@app.get("/")
def read_root():
    return {"status": "running", "message": "API is online."}

@app.get("/download")
def extract_media(url: str = Query(..., description="The social media URL to extract")):
    if not url:
        raise HTTPException(status_code=400, detail="URL parameter is required.")

    ydl_opts = {
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Fetch-Mode': 'navigate',
        },
        'skip_download': True,        
        'extract_flat': False,        
        'dump_single_json': True,     
        'no_warnings': True,
        'quiet': True,
        'ignoreerrors': True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise HTTPException(status_code=400, detail="Could not extract data from this URL. It may be private or invalid.")
                
            sanitized_info = ydl.sanitize_info(info)
            
            # --- 1. Gather all high-res/base images safely ---
            images = []
            if 'thumbnail' in sanitized_info and sanitized_info['thumbnail']:
                images.append(sanitized_info['thumbnail'])
            if 'thumbnails' in sanitized_info:
                for t in sanitized_info['thumbnails']:
                    if 'url' in t:
                        images.append(t['url'])
                        
            if 'entries' in sanitized_info:
                for entry in sanitized_info['entries']:
                    if entry:
                        if 'url' in entry and any(ext in entry['url'].lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', 'heic']):
                            images.append(entry['url'])
                        if 'thumbnail' in entry and entry['thumbnail']:
                            images.append(entry['thumbnail'])
                        if 'thumbnails' in entry:
                            images.extend([t['url'] for t in entry['thumbnails'] if 'url' in t])

            images = list(dict.fromkeys(images))

            # --- 2. Isolate Video and Audio Download Streams Safely ---
            video_link = None
            audio_link = None
            
            formats = sanitized_info.get('formats', [])
            if formats:
                video_formats = [f for f in formats if f.get('vcodec') != 'none' and f.get('url')]
                if video_formats:
                    video_link = video_formats[-1]['url']
                
                audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none' and f.get('url')]
                if audio_formats:
                    audio_link = audio_formats[-1]['url']
            
            if not video_link and sanitized_info.get('url'):
                root_url = sanitized_info['url']
                if not any(ext in root_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                    video_link = root_url

            # --- 3. Extract Metadata Fields ---
            main_thumbnail = sanitized_info.get("thumbnail") or (images if images else None)
            author = (
                sanitized_info.get("uploader") or 
                sanitized_info.get("uploader_id") or 
                sanitized_info.get("channel") or 
                sanitized_info.get("author")
            )
            platform = sanitized_info.get("extractor_key") or sanitized_info.get("extractor")
            title = sanitized_info.get("title") or sanitized_info.get("description", "")[:50]

            # --- 4. Structure Output Dynamically ---
            is_video = video_link is not None

            if is_video:
                # Video JSON layout format
                return {
                    "success": True,
                    "platform": platform,
                    "title": title,
                    "author": author,
                    "thumbnail": main_thumbnail,
                    "video_link": video_link,
                    "audio_link": audio_link,
                    "images": None
                }
            else:
                # Pure Image JSON layout format (No thumbnail, video link, or audio link keys)
                return {
                    "success": True,
                    "platform": platform,
                    "title": title,
                    "author": author,
                    "images": images
                }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
