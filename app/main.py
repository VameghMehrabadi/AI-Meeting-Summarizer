"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse

from app.core.config import UPLOAD_DIR
from app.db.database import init_db
from app.api import meetings, reports, pipeline

ROOT_INDEX = Path(__file__).resolve().parent.parent / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create database tables
    init_db()
    yield
    # Shutdown: nothing to clean up


app = FastAPI(title="AI Meeting Summarizer & Action Tracker", lifespan=lifespan)

# Static + templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Routers
app.include_router(meetings.router)
app.include_router(reports.router)
app.include_router(pipeline.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return FileResponse(ROOT_INDEX, media_type="text/html")


@app.get("/meetings", response_class=HTMLResponse)
async def meetings_list_page(request: Request):
    return templates.TemplateResponse("list.html", {"request": request})


@app.get("/meetings/{meeting_id}", response_class=HTMLResponse)
async def meeting_report_page(request: Request, meeting_id: int):
    return templates.TemplateResponse("report.html", {"request": request, "meeting_id": meeting_id})
