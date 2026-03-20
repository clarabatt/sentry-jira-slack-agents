from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from routers.alerts import router as alerts_router
from pathlib import Path

app = FastAPI(
    title="Sentry Rotation AI Agent — POC",
    description="Multi-agent system for automated Sentry triage",
    version="0.1.0",
)

app.include_router(alerts_router)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
async def serve_ui():
    return FileResponse("static/index.html")
