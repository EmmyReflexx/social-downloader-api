import os
import re
import cv2
import numpy as np
from io import BytesIO
import base64
import requests
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, File, UploadFile, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
from PIL import Image, ImageEnhance, ImageFilter
import qrcode
from qrcode import QRCode
from qrcode.image.pil import PilImage

app = FastAPI(title="Social Media Direct Video Extractor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'

DOWNLOAD_DIR = os.path.abspath("./downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def remove_file(path: str):
    """Background task to delete the temporary file after it is sent to the user."""
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

def sanitize_filename(name: str) -> str:
    """Removes special characters, spaces, and emojis to ensure a safe file system path."""
    if not name:
        return "video"
    clean = re.sub(r'[^a-zA-Z0-9\s\-_]', '', name)
    clean = re.sub(r'\s+', '_', clean).strip('_')
    return clean[:50]

def preprocess_image_for_scanning(image):
    """Advanced image preprocessing for better QR detection"""
    # Convert to grayscale
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    
    # Apply multiple preprocessing techniques to handle various quality issues
    processed_images = []
    
    # 1. Original grayscale
    processed_images.append(gray)
    
    # 2. Contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)
    processed_images.append(enhanced)
    
    # 3. Adaptive threshold
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY, 11, 2)
    processed_images.append(thresh)
    
    # 4. Sharpening
    kernel = np.array([[-1,-1,-1],
                       [-1, 9,-1],
                       [-1,-1,-1]])
    sharpened = cv2.filter2D(gray, -1, kernel)
    processed_images.append(sharpened)
    
    # 5. Denoising
    denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
    processed_images.append(denoised)
    
    # 6. Resize if too small
    if gray.shape[0] < 100 or gray.shape[1] < 100:
        scale_factor = max(2, 400 / min(gray.shape[0], gray.shape[1]))
        new_size = (int(gray.shape[1] * scale_factor), int(gray.shape[0] * scale_factor))
        resized = cv2.resize(gray, new_size, interpolation=cv2.INTER_CUBIC)
        processed_images.append(resized)
    
    return processed_images

def decode_qr_barcode_from_image(image_data):
    """Advanced QR decoding with multiple attempts and preprocessing (no external libs needed)"""
    try:
        # Try with PIL first (most reliable for QR codes)
        try:
            pil_image = Image.open(BytesIO(image_data))
            
            # Convert to grayscale
            pil_image = pil_image.convert('L')
            
            # Try different contrast levels
            for factor in [1.0, 1.5, 2.0, 0.5]:
                try:
                    enhancer = ImageEnhance.Contrast(pil_image)
                    enhanced = enhancer.enhance(factor)
                    
                    # Try to decode QR from PIL image
                    from qrcode import QRCode
                    qr = QRCode()
                    decoded = qrcode.decode(enhanced)
                    if decoded:
                        return decoded.data.decode('utf-8')
                except:
                    continue
        except:
            pass
        
        # Then try with OpenCV preprocessing
        image = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return None
        
        processed_versions = preprocess_image_for_scanning(image)
        
        for processed_img in processed_versions:
            try:
                # Convert to PIL for QR decoding
                pil_img = Image.fromarray(processed_img)
                
                # Try QR decoding
                from qrcode import QRCode
                qr = QRCode()
                decoded = qrcode.decode(pil_img)
                if decoded:
                    return decoded.data.decode('utf-8')
            except:
                continue
        
        return None
    except Exception as e:
        print(f"QR scanning error: {str(e)}")
        return None

def extract_image_data(image_input):
    """Extract raw image data from various input formats"""
    if isinstance(image_input, str):
        # Remove data URL prefix if present
        if ',' in image_input:
            if image_input.startswith('data:'):
                image_input = image_input.split(',', 1)[1]
            else:
                pass
        
        try:
            return base64.b64decode(image_input)
        except:
            pass
    
    if isinstance(image_input, bytes):
        return image_input
    
    return None

@app.get("/")
def home():
    return {
        "message": "Extractor API is online.",
        "endpoints": {
            "metadata_extraction": "/extract?url=YOUR_URL",
            "physical_download": "/download?url=YOUR_URL&quality=best",
            "qr_barcode_scan_url": "/scan-code?image_url=IMAGE_URL",
            "qr_barcode_scan_base64": "/scan-code?image_base64=BASE64_ENCODED_IMAGE",
            "qr_barcode_scan_full": "/scan-code?image=FULL_IMAGE_STRING"
        }
    }

@app.get("/download")
def download_video(
    background_tasks: BackgroundTasks,
    url: str = Query(..., description="The social media video URL to download directly"),
    quality: str = Query("best", description="Choose the video quality: 'best' or 'worst'")
):
    """
    Downloads the video in either best or worst resolution quality and serves it 
    named after the title as an instant browser attachment file.
    """
    quality = quality.lower().strip()
    if quality == "worst":
        format_selector = "worstvideo+worstaudio/worst"
    else:
        format_selector = "best"

    pre_opts = {
        'quiet': True,
        'no_warnings': True,
        'http_headers': {'User-Agent': USER_AGENT}
    }
    
    try:
        with yt_dlp.YoutubeDL(pre_opts) as ydl_pre:
            meta = ydl_pre.extract_info(url, download=False)
            video_title = meta.get("title") or meta.get("description", "")[:30] or "social_video"
            safe_title = sanitize_filename(video_title)
    except Exception:
        safe_title = "social_video"

    output_template = os.path.join(DOWNLOAD_DIR, f'{safe_title}_%(id)s.%(ext)s')

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': format_selector,
        'outtmpl': output_template,
        'http_headers': {
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,video/webm,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            _, actual_ext = os.path.splitext(filename)
            actual_ext = actual_ext or ".mp4"
            
            if not os.path.exists(filename):
                raise HTTPException(status_code=500, detail="Downloaded file was not found on disk.")

            background_tasks.add_task(remove_file, filename)
            download_name = f"{safe_title}{actual_ext}"

            return FileResponse(
                path=filename, 
                media_type='application/octet-stream', 
                filename=download_name
            )

    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"yt-dlp Download Error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/extract")
def extract_metadata(url: str = Query(..., description="The social media video URL to extract info from")):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'best',
        'http_headers': {
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,video/webm,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise HTTPException(status_code=404, detail="Could not extract metadata from this URL.")

            formats = info.get("formats", [])
            
            # Fixed file size extraction - try multiple methods
            valid_sizes = []
            for f in formats:
                size = f.get("filesize") or f.get("filesize_approx")
                if size:
                    valid_sizes.append(size)
                if not size and f.get("http_headers"):
                    content_length = f.get("http_headers", {}).get("Content-Length")
                    if content_length:
                        try:
                            valid_sizes.append(int(content_length))
                        except (ValueError, TypeError):
                            pass
            
            best_size = max(valid_sizes) if valid_sizes else None
            worst_size = min(valid_sizes) if valid_sizes else None

            audio_size = None
            for f in formats:
                if f.get("vcodec") == "none" and f.get("acodec") != "none" and f.get("url"):
                    audio_size = f.get("filesize") or f.get("filesize_approx")
                    if not audio_size and f.get("http_headers"):
                        content_length = f.get("http_headers", {}).get("Content-Length")
                        if content_length:
                            try:
                                audio_size = int(content_length)
                            except (ValueError, TypeError):
                                pass
                    break

            response_data = {
                "title": info.get("title") or info.get("description", "")[:50] or "Social Media Video",
                "author": info.get("uploader") or info.get("channel") or "Unknown",
                "platform": info.get("extractor_key") or "Unknown",
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "best_filesize_bytes": best_size,
                "worst_filesize_bytes": worst_size,
                "audio_filesize_bytes": audio_size,
                "video_link": None,
                "audio_link": None,
                "images": False
            }

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
                video_link = info.get("url")

            response_data["video_link"] = video_link
            response_data["audio_link"] = audio_link or video_link
            
            return response_data

    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"yt-dlp Extraction Error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/scan-code")
async def scan_code(
    image_url: str = Query(None, description="URL of the image containing QR code"),
    image_base64: str = Query(None, description="Base64 encoded image data"),
    image: str = Query(None, description="Full image string (base64 with or without data URL prefix)")
):
    """
    Scan QR code from an image. Just access this URL in your browser!
    """
    if not image_url and not image_base64 and not image:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Missing image source",
                "usage": "Use one of these:",
                "options": [
                    "?image_url=IMAGE_URL",
                    "?image_base64=BASE64_IMAGE_DATA",
                    "?image=FULL_IMAGE_STRING"
                ],
                "example": "/scan-code?image=data:image/png;base64,iVBORw0KGgo..."
            }
        )
    
    try:
        image_data = None
        
        if image:
            image_data = extract_image_data(image)
        
        if not image_data and image_base64:
            image_data = extract_image_data(image_base64)
        
        if not image_data and image_url:
            headers = {'User-Agent': USER_AGENT}
            response = requests.get(image_url, headers=headers, timeout=30)
            response.raise_for_status()
            image_data = response.content
        
        if not image_data:
            return JSONResponse(
                status_code=400,
                content={"error": "Could not retrieve or decode image data"}
            )
        
        result = decode_qr_barcode_from_image(image_data)
        
        if result:
            return JSONResponse(content={"code_text": result})
        else:
            return JSONResponse(
                status_code=404,
                content={"error": "No QR code found in the image"}
            )
            
    except requests.exceptions.RequestException as e:
        return JSONResponse(
            status_code=400,
            content={"error": f"Error downloading image: {str(e)}"}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error processing image: {str(e)}"}
        )

@app.post("/scan-code")
async def scan_code_from_upload(
    file: UploadFile = File(None, description="Image file containing QR code"),
    image_base64: str = Form(None, description="Base64 encoded image data"),
    image: str = Form(None, description="Full image string")
):
    """Scan QR code from uploaded file or base64 data."""
    try:
        image_data = None
        
        if file and file.filename:
            contents = await file.read()
            if contents:
                image_data = contents
        
        if not image_data and image:
            image_data = extract_image_data(image)
        
        if not image_data and image_base64:
            image_data = extract_image_data(image_base64)
        
        if not image_data:
            return JSONResponse(
                status_code=400,
                content={"error": "No image data provided"}
            )
        
        result = decode_qr_barcode_from_image(image_data)
        
        if result:
            return JSONResponse(content={"code_text": result})
        else:
            return JSONResponse(
                status_code=404,
                content={"error": "No QR code found in the image"}
            )
            
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error processing image: {str(e)}"}
        )

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
