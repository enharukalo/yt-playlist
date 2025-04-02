from dotenv import load_dotenv

load_dotenv()

import logging
import os
from typing import Annotated, Optional

from fastapi import FastAPI, Form, Request, HTTPException, status
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import traceback
import datetime

from src.itemlist import ItemList
from src.utils import find_time_slice

# Get the API key and convert to list if it contains semicolons
YOUTUBE_APIS = os.environ["APIS"].split(";") if ";" in os.environ["APIS"] else [os.environ["APIS"]]

# Configure logging to console only
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

fapp = FastAPI(
    title="YouTube Playlist Length Calculator",
    description="Calculate the total duration of YouTube playlists",
    version="1.0.0"
)

fapp.mount("/static", StaticFiles(directory="static", html=True), name="static")

templates = Jinja2Templates(directory="templates")

# Add security middlewares
fapp.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yt-playlist-length.enhar.net", "https://yt-playlist-428z.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fapp.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=[
        "yt-playlist-length.enhar.net",
        "yt-playlist-428z.onrender.com",
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "localhost:8000",
        "127.0.0.1:8000",
        "0.0.0.0:8000",
        "localhost:10000",
        "127.0.0.1:10000",
        "0.0.0.0:10000"
    ]
)

# Add compression
fapp.add_middleware(GZipMiddleware, minimum_size=1000)

# Add caching headers
@fapp.middleware("http")
async def add_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response

# Add security headers middleware
@fapp.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@fapp.get("/", response_class=HTMLResponse)
async def home(request: Request):
    response = templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "playlist_detail": []  # Always empty since we're using AJAX
        }
    )
    
    # Add cache control headers
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response


@fapp.post("/")
async def home(
    request: Request,
    search_string: Annotated[str, Form(min_length=10)],
    range_start: Annotated[Optional[str], Form()],
    range_end: Annotated[Optional[str], Form()],
    custom_speed: Annotated[Optional[str], Form()],
    youtube_api: Annotated[Optional[str], Form()],
):
    try:
        # Validate search string
        lines = search_string.strip().split('\n')
        if len(lines) > 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many URLs provided"
            )
        
        for line in lines:
            if line.strip() and len(line.strip()) < 10:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid URL length"
                )

        range_start = int(range_start) if range_start else 1
        range_end = int(range_end) if range_end else 500
        custom_speed = float(custom_speed) if custom_speed else None

        if custom_speed and (custom_speed < 0.1 or custom_speed > 10):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid playback speed"
            )

        logger.info(f"Input TS({find_time_slice()}): {search_string}")
        youtube_api = youtube_api if youtube_api else YOUTUBE_APIS[find_time_slice() % len(YOUTUBE_APIS)]
        items = ItemList(
            search_string, range_start, range_end, custom_speed, youtube_api
        )
        await items.do_async_work()
        output = items.get_output_string()

        # Return JSON response
        return {"playlist_detail": output}

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request"
        )


@fapp.get("/healthz", response_model=dict)
async def healthz():
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "version": "1.0.0"
    }


@fapp.get("/ads.txt", response_class=PlainTextResponse)
def static_from_root_google():
    return "google.com, pub-9035466269332608, DIRECT, f08c47fec0942fa0"


@fapp.get("/robots.txt", response_class=PlainTextResponse)
async def get_robots_txt():
    return """User-agent: *
Allow: /
Sitemap: https://yt-playlist-length.enhar.net/sitemap.xml"""


@fapp.get("/sitemap.xml")
async def get_sitemap():
    # Get current date in YYYY-MM-DD format
    current_date = datetime.date.today().isoformat() 
    
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://yt-playlist-length.enhar.net/</loc>
        <lastmod>{current_date}</lastmod>
        <changefreq>weekly</changefreq>
        <priority>1.0</priority>
    </url>
</urlset>"""
    return Response(
        content=content,
        media_type="application/xml"
    )


if __name__ == "__main__":
    fapp.run(
        use_reloader=True, debug=False, host="0.0.0.0", port=10000, access_log=False
    )
