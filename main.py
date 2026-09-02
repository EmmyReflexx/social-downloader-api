import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

app = FastAPI(title="Social Media Media Extractor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "Extractor API is running. Use /download or /extract with ?url=YOUR_URL"}

@app.get("/download")
@app.get("/extract")
def extract_media(url: str = Query(..., description="The social media URL to extract")):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
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

            # Base metadata payload
            response_data = {
                "title": info.get("title") or info.get("description", "")[:50] or "Social Media Post",
                "author": info.get("uploader") or info.get("channel") or "Unknown",
                "thumbnail": info.get("thumbnail"),
            }

            formats = info.get("formats", [])
            entries = info.get("entries")

            # --- CASE 1: MULTI-IMAGE CAROUSELS / SUB-ENTRIES ---
            if entries:
                image_links = []
                for entry in entries:
                    if entry:
                        # Scan deep for direct image files inside nested playlist items
                        img_url = entry.get("url") or entry.get("thumbnail")
                        if img_url and not any(vid_ext in img_url for vid_ext in [".mp4", ".m3u8"]):
                            image_links.append(img_url)
                
                if image_links:
                    response_data["images"] = image_links
                    return response_data

            # --- CASE 2: VIDEO EXTRACTOR (Your Perfect Video Code) ---
            if formats:
                video_link = None
                audio_link = None

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
                    root_url = info.get("url")
                    if root_url and not any(ext in root_url for ext in [".jpg", ".png", ".webp"]):
                        video_link = root_url

                if video_link:
                    response_data["video_link"] = video_link
                    response_data["audio_link"] = audio_link or video_link
                    return response_data

            # --- CASE 3: STATIC SINGLE IMAGE / EXTENDED FALLBACK ---
            # If it bypasses the video streams, extract the absolute highest resolution image URLs available
            image_links = []
            
            # Check requested downloads array (where yt-dlp puts raw carousel items sometimes)
            req_downloads = info.get("requested_downloads", [])
            for download in req_downloads:
                if download and download.get("url"):
                    image_links.append(download.get("url"))

            # Check raw thumbnails array
            thumbnails = info.get("thumbnails", [])
            if thumbnails and not image_links:
                image_links = [t.get("url") for t in thumbnails if t.get("url")]
            
            # Absolute root fallbacks
            if not image_links and info.get("thumbnail"):
                image_links.append(info.get("thumbnail"))
                
            if not image_links and info.get("url"):
                image_links.append(info.get("url"))

            # Filter out any lingering video stream chunks from your images list
            clean_images = [link for link in image_links if link and not any(vid_ext in link for vid_ext in [".mp4", ".m3u8", ".mpd", "mime=video"])]
            
            response_data["images"] = clean_images
            return response_data

    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"yt-dlp Extraction Error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server Processing Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
