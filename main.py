import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import yt_dlp

app = FastAPI(title="Social Media Unified Video Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'

def get_ytdl_instance(url: str):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'best',
        'impersonate': 'chrome-131',
    }
    try:
        return yt_dlp.YoutubeDL(ydl_opts)
    except Exception:
        ydl_opts.pop('impersonate', None)
        referer = "https://tiktok.com" if "tiktok.com" in url.lower() else "https://instagram.com"
        ydl_opts['http_headers'] = {
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': referer
        }
        return yt_dlp.YoutubeDL(ydl_opts)

# --------------------------------------------------------------------
# 1. METADATA EXTRACTOR ROUTES (/extract & /download)
# --------------------------------------------------------------------
@app.get("/extract")
@app.get("/download")
def extract_video_metadata(url: str = Query(..., description="The social media URL to extract metadata from")):
    ydl = get_ytdl_instance(url)
    try:
        info = ydl.extract_info(url, download=False)
        if not info:
            raise HTTPException(status_code=404, detail="Could not extract metadata.")

        video_link = info.get("url")
        formats = info.get("formats", [])
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

        if not video_link:
            video_link = info.get("url")

        if video_link:
            # FIXED: Hardcoding your exact Render live domain link so it never falls back to localhost
            production_host = "https://social-downloader-api-grt8.onrender.com"
            proxy_video_url = f"{production_host}/stream?url={url}"
            
            return {
                "title": info.get("title") or info.get("description", "")[:50] or "Social Media Video",
                "author": info.get("uploader") or info.get("channel") or "Unknown",
                "thumbnail": info.get("thumbnail"),
                "video_link": proxy_video_url,
                "audio_link": audio_link or proxy_video_url,
                "images": False 
            }
        else:
            raise HTTPException(status_code=400, detail="No downloadable link detected.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Metadata Extraction Error: {str(e)}")
    finally:
        ydl.close()

# --------------------------------------------------------------------
# 2. BULLETPROOF STREAMING PROXY ROUTE (/stream)
# --------------------------------------------------------------------
@app.get("/stream")
def stream_video(url: str = Query(..., description="The social media video URL to stream")):
    ydl = get_ytdl_instance(url)
    try:
        info = ydl.extract_info(url, download=False)
        if not info:
            raise HTTPException(status_code=404, detail="Could not extract metadata.")

        video_link = info.get("url")
        formats = info.get("formats", [])

        if not video_link and formats:
            for f in formats:
                if f.get("vcodec") != "none" and f.get("acodec") != "none" and f.get("url"):
                    video_link = f.get("url")
                    break
            if not video_link:
                video_formats = [f for f in formats if f.get("vcodec") != "none" and f.get("url")]
                if video_formats:
                    video_link = video_formats[-1].get("url")

        if not video_link:
            raise HTTPException(status_code=400, detail="No downloadable link detected.")

        response_stream = ydl.urlopen(video_link)
        
        def chunk_generator(stream, ydl_instance):
            try:
                while True:
                    chunk = stream.read(1024 * 64)  
                    if not chunk:
                        break
                    yield chunk
            finally:
                stream.close()        
                ydl_instance.close()  

        safe_title = "".join([c for c in (info.get("title") or "video") if c.isalnum() or c in (' ', '_', '-')]).rstrip()
        filename = f"{safe_title[:30]}.mp4"

        return StreamingResponse(
            chunk_generator(response_stream, ydl), 
            media_type="video/mp4",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-cache"
            }
        )

    except Exception as e:
        ydl.close()
        raise HTTPException(status_code=500, detail=f"Streaming Server Error: {str(e)}")

@app.get("/")
def home():
    return {
        "message": "Unified Video API is running.",
        "endpoints": {
            "metadata_extraction": "/extract?url=YOUR_URL or /download?url=YOUR_URL",
            "unblocked_streaming": "/stream?url=YOUR_URL"
        }
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
