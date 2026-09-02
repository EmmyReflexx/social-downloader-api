import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

app = FastAPI(title="Social Media Video Extractor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "Video Extractor API is online. Use /download or /extract with ?url=YOUR_URL"}

@app.get("/download")
@app.get("/extract")
def extract_video(url: str = Query(..., description="The social media video URL to extract")):
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        # 'format': 'best' forces yt-dlp to grab a universally compatible single stream link
        'format': 'best',
        'http_headers': {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,video/webm,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Fetch-Mode': 'navigate',
            'Referer': 'https://tiktok.com',
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                raise HTTPException(status_code=404, detail="Could not extract metadata from this URL.")

            # Base metadata schema
            response_data = {
                "title": info.get("title") or info.get("description", "")[:50] or "Social Media Video",
                "author": info.get("uploader") or info.get("channel") or "Unknown",
                "thumbnail": info.get("thumbnail"),
            }

            # TikTok specific check: TikTok usually stores its raw best direct link in info['url']
            video_link = info.get("url")
            audio_link = None

            formats = info.get("formats", [])
            
            # If root url isn't found, look through formats list instead
            if not video_link and formats:
                for f in formats:
                    if f.get("vcodec") != "none" and f.get("acodec") != "none" and f.get("url"):
                        video_link = f.get("url")
                        break
                
                if not video_link:
                    video_formats = [f for f in formats if f.get("vcodec") != "none" and f.get("url")]
                    if video_formats:
                        video_link = video_formats[-1].get("url")

            # Try to grab independent audio if available
            for f in formats:
                if f.get("vcodec") == "none" and f.get("acodec") != "none" and f.get("url"):
                    audio_link = f.get("url")
                    break

            if video_link:
                response_data["video_link"] = video_link
                response_data["audio_link"] = audio_link or video_link
                return response_data
            else:
                raise HTTPException(status_code=400, detail="Could not extract direct video streaming links.")

    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"yt-dlp Extraction Error: {str(e)}")
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
