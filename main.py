import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

app = FastAPI(title="Social Media Video & Image Extractor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "Extractor API is online. Use /download or /extract with ?url=YOUR_URL"}

@app.get("/download")
@app.get("/extract")
def extract_media(url: str = Query(..., description="The social media URL to extract")):
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    
    # We turn ON ignoreerrors so yt-dlp doesn't throw a hard crash on images, 
    # allowing us to read the basic page metadata it managed to scrape.
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,  
        'http_headers': {
            'User-Agent': user_agent,
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

            # Base structural payload schema
            response_data = {
                "title": info.get("title") or info.get("description", "")[:50] or "Social Media Post",
                "author": info.get("uploader") or info.get("channel") or "Unknown",
                "thumbnail": info.get("thumbnail"),
            }

            formats = info.get("formats", [])
            
            # Check if there are playable video tracks available
            has_video_formats = any(f.get("vcodec") != "none" and f.get("url") for f in formats)

            # ----------------------------------------------------
            # 1. PERFECT VIDEO POST LOGIC
            # ----------------------------------------------------
            if has_video_formats:
                video_link = None
                audio_link = None

                # Look for combined streaming formats first
                for f in formats:
                    if f.get("vcodec") != "none" and f.get("acodec") != "none" and f.get("url"):
                        video_link = f.get("url")
                        break

                # Fallback to the highest resolution single stream track
                if not video_link:
                    video_formats = [f for f in formats if f.get("vcodec") != "none" and f.get("url")]
                    if video_formats:
                        video_link = video_formats[-1].get("url")

                # Isolate the independent audio layer
                for f in formats:
                    if f.get("vcodec") == "none" and f.get("acodec") != "none" and f.get("url"):
                        audio_link = f.get("url")
                        break

                if not video_link:
                    video_link = info.get("url")

                response_data["video_link"] = video_link
                response_data["audio_link"] = audio_link or video_link
                response_data["images"] = False  # Fixed layout flag for pure video objects
                return response_data

            # ----------------------------------------------------
            # 2. OUR OWN SIMPLE IMAGE EXTRACTOR LOGIC
            # ----------------------------------------------------
            else:
                image_links = []
                
                # Check 1: Nested entries (for carousels/galleries on Reddit/Twitter)
                entries = info.get("entries") or info.get("requested_downloads") or []
                for entry in entries:
                    if entry:
                        img_url = entry.get("url") or entry.get("thumbnail")
                        if img_url:
                            image_links.append(img_url)

                # Check 2: If entries are flat, pull all available thumbnail objects (Instagram fallback)
                if not image_links:
                    thumbnails = info.get("thumbnails") or []
                    for t in thumbnails:
                        if t.get("url"):
                            image_links.append(t.get("url"))

                # Check 3: Root layout url fallback
                if not image_links and info.get("url"):
                    image_links.append(info.get("url"))

                # Filter out empty entries and any stray video stream parts
                clean_images = []
                for link in image_links:
                    if link and not any(vid_ext in link.lower() for vid_ext in [".mp4", ".m3u8", ".mpd", "mime=video"]):
                        if link not in clean_images:  # Remove duplicates
                            clean_images.append(link)

                # Format the response object exactly to match your JSON expectations
                response_data["video_link"] = None
                response_data["audio_link"] = None
                response_data["images"] = clean_images if clean_images else [info.get("thumbnail")]
                
                return response_data

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server Processing Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
