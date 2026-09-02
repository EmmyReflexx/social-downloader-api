import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import yt_dlp

app = FastAPI(title="Social Media Streaming Video Extractor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "API is online. Use /stream with ?url=YOUR_URL"}

@app.get("/stream")
def stream_video(url: str = Query(..., description="The social media video URL to stream")):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'best',
        'impersonate': 'chrome-131', 
    }

    # Instantiate yt-dlp outside of a context manager 
    # to keep it alive during the streaming lifespan
    ydl = yt_dlp.YoutubeDL(ydl_opts)

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

        # Open the network stream through yt-dlp's underlying session
        response_stream = ydl.urlopen(video_link)
        
        # --- FIXED: Generator safely cleans up BOTH the stream and yt-dlp instances ---
        def chunk_generator(stream, ydl_instance):
            try:
                while True:
                    chunk = stream.read(1024 * 64) # 64KB blocks keep memory flat
                    if not chunk:
                        break
                    yield chunk
            finally:
                stream.close()        # Closes the connection to the video CDN
                ydl_instance.close()  # Safely closes the yt-dlp internal connection pool

        # Sanitize filename for browser attachment headers
        safe_title = "".join([c for c in (info.get("title") or "video") if c.isalnum() or c in (' ', '_', '-')]).rstrip()
        filename = f"{safe_title[:30]}.mp4"

        # Stream chunks progressively directly into the browser pipeline
        return StreamingResponse(
            chunk_generator(response_stream, ydl), 
            media_type="video/mp4",
            headers={
                "Content-Disposition": f"attachment; filename='{filename}'",
                "Cache-Control": "no-cache"
            }
        )

    except Exception as e:
        # If an error happens BEFORE streaming starts, make sure to close the ydl instance
        ydl.close()
        raise HTTPException(status_code=500, detail=f"Server Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
