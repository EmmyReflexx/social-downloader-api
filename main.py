import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

app = FastAPI(title="Social Media Header-Passing Video Extractor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'

@app.get("/")
def home():
    return {"message": "API is online. Use /download or /extract with ?url=YOUR_URL"}

@app.get("/download")
@app.get("/extract")
def extract_video(url: str = Query(..., description="The social media video URL to extract")):
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'best',
        'http_headers': {
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Fetch-Mode': 'navigate',
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise HTTPException(status_code=404, detail="Could not extract metadata.")

            formats = info.get("formats", [])
            video_link = info.get("url")
            audio_link = None

            if not video_link and formats:
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

            if video_link:
                # Dynamically set the Referer based on the input URL
                referer = "https://tiktok.com" if "tiktok.com" in url.lower() else "https://instagram.com"
                
                # We return the direct link AND the exact headers your JS frontend needs to send
                return {
                    "title": info.get("title") or info.get("description", "")[:50] or "Social Media Video",
                    "author": info.get("uploader") or info.get("channel") or "Unknown",
                    "thumbnail": info.get("thumbnail"),
                    "video_link": video_link,
                    "audio_link": audio_link or video_link,
                    "required_headers": {
                        "User-Agent": USER_AGENT,
                        "Referer": referer
                    }
                }
            else:
                raise HTTPException(status_code=400, detail="No downloadable link detected.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
