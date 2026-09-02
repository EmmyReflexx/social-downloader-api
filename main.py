import os
import subprocess
import json
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

app = FastAPI(title="Social Media Hybrid Media Extractor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def extract_images_via_gallery_dl(url: str) -> list:
    """
    Spawns gallery-dl as a clean subprocess to extract image URLs 
    using the exact text output formatting array (-g / --get-urls).
    """
    try:
        # -g returns only the raw direct source URLs to stdout line-by-line
        # --ignore-errors prevents catastrophic script termination
        cmd = ["gallery-dl", "-g", "--ignore-errors", url]
        
        result = subprocess.run(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True, 
            timeout=25
        )
        
        if result.stdout:
            # Split the line breaks and clear any empty strings or non-http anomalies
            links = [line.strip() for line in result.stdout.split('\n') if line.strip().startswith("http")]
            return links
        return []
    except Exception:
        return []

@app.get("/")
def home():
    return {"message": "Hybrid Extractor API is running. Use /download or /extract?url=YOUR_URL"}

@app.get("/download")
@app.get("/extract")
def extract_media(url: str = Query(..., description="The social media URL to extract")):
    # Base user agent string profile to route through standard headers
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'http_headers': {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise HTTPException(status_code=404, detail="Could not retrieve platform response headers.")

            # Compile structural identity parameters
            response_data = {
                "title": info.get("title") or info.get("description", "")[:50] or "Social Media Post",
                "author": info.get("uploader") or info.get("channel") or "Unknown",
                "thumbnail": info.get("thumbnail"),
            }

            formats = info.get("formats", [])

            # ----------------------------------------------------
            # ENGINE CHANGER ENGINE: IS IT A VIDEO POST?
            # ----------------------------------------------------
            # If valid audio/video container stream indices are mapped out by yt-dlp
            has_video_formats = any(f.get("vcodec") != "none" and f.get("url") for f in formats)

            if has_video_formats and info.get("url") and not any(ext in info.get("url", "") for ext in [".jpg", ".png", ".webp"]):
                video_link = None
                audio_link = None

                # 1. Grab integrated stream audio + video trackers
                for f in formats:
                    if f.get("vcodec") != "none" and f.get("acodec") != "none" and f.get("url"):
                        video_link = f.get("url")
                        break

                # 2. Pick the absolute highest standalone track if tracking separate files
                if not video_link:
                    video_formats = [f for f in formats if f.get("vcodec") != "none" and f.get("url")]
                    if video_formats:
                        video_link = video_formats[-1].get("url")

                # 3. Pull standalone voice array 
                for f in formats:
                    if f.get("vcodec") == "none" and f.get("acodec") != "none" and f.get("url"):
                        audio_link = f.get("url")
                        break

                if not video_link:
                    video_link = info.get("url")

                response_data["video_link"] = video_link
                response_data["audio_link"] = audio_link or video_link
                return response_data

            # ----------------------------------------------------
            # ENGINE CHANGER ENGINE: IS IT AN IMAGE / CAROUSEL POST?
            # ----------------------------------------------------
            else:
                # Fire gallery-dl pipeline to safely crawl out structural layout resources
                images = extract_images_via_gallery_dl(url)
                
                # If gallery-dl successfully grabbed clean links, drop them in
                if images:
                    response_data["images"] = images
                else:
                    # Smart fallback loop just in case gallery-dl yields an empty list
                    fallback_links = []
                    thumbnails = info.get("thumbnails", [])
                    if thumbnails:
                        fallback_links = [t.get("url") for t in thumbnails if t.get("url")]
                    if not fallback_links and info.get("thumbnail"):
                        fallback_links.append(info.get("thumbnail"))
                    
                    response_data["images"] = [l for l in fallback_links if l and not any(v in l for v in [".mp4", ".m3u8"])]

                return response_data

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Hybrid Routing Engine Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
