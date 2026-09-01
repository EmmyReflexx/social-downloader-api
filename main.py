import os
from fastapi import FastAPI, HTTPException, Query
from yt_dlp import YoutubeDL

app = FastAPI(
    title="Social Media Media Extractor API",
    description="Clean API to grab clean download links and images from social networks"
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
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            sanitized_info = ydl.sanitize_info(info)
            
            # --- 1. Gather all high-res/base images safely ---
            images = []
            if 'thumbnail' in sanitized_info and sanitized_info['thumbnail']:
                images.append(sanitized_info['thumbnail'])
            if 'thumbnails' in sanitized_info:
                for t in sanitized_info['thumbnails']:
                    if 'url' in t:
                        images.append(t['url'])
                        
            # Pull image arrays out of slider/carousel posts (Instagram/Reddit)
            if 'entries' in sanitized_info:
                for entry in sanitized_info['entries']:
                    if entry and 'thumbnail' in entry:
                        images.append(entry['thumbnail'])
                    if entry and 'thumbnails' in entry:
                        images.extend([t['url'] for t in entry['thumbnails'] if 'url' in t])

            # Clean and deduplicate image urls
            images = list(dict.fromkeys(images))

            # --- 2. Isolate Video and Audio Download Streams ---
            video_link = None
            audio_link = None
            
            # If yt-dlp extracted direct download formats (YouTube, TikTok, Facebook, etc.)
            formats = sanitized_info.get('formats', [])
            
            # Find the best standalone video (or combined video+audio stream)
            video_formats = [f for f in formats if f.get('vcodec') != 'none' and f.get('url')]
            if video_formats:
                # Target the highest quality available format URL
                video_link = video_formats[-1]['url']
            elif sanitized_info.get('url'):
                # Fallback if there's only one direct asset URL at the root level
                video_link = sanitized_info['url']

            # Find the best audio-only stream (for background tracking or music)
            audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none' and f.get('url')]
            if audio_formats:
                audio_link = audio_formats[-1]['url']

            # --- 3. Extract Meta Details ---
            main_thumbnail = sanitized_info.get("thumbnail") or (images[0] if images else None)
            
            author = (
                sanitized_info.get("uploader") or 
                sanitized_info.get("uploader_id") or 
                sanitized_info.get("channel") or 
                sanitized_info.get("author")
            )
            
            platform = sanitized_info.get("extractor_key") or sanitized_info.get("extractor")

            # --- 4. Clean Payload Response ---
            return {
                "success": True,
                "platform": platform,
                "title": sanitized_info.get("title") or sanitized_info.get("description", "")[:50],
                "author": author,
                "thumbnail": main_thumbnail,
                "video_link": video_link,
                "audio_link": audio_link,
                "images": images
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
