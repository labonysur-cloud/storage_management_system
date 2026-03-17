from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import get_settings
from app.services.anthropic_service import AnthropicService
from app.services.storage_manager import StorageManager


settings = get_settings()
storage_manager = StorageManager(settings)
anthropic_service = AnthropicService(settings)
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

app = FastAPI(title="Unified Storage Management System", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("settings.html", {"request": request})


@app.get("/api-access", response_class=HTMLResponse)
async def api_access_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("api_access.html", {"request": request})


@app.get("/api/health")
async def health() -> dict[str, str | list[str]]:
    return {
        "status": "ok",
        "providers": storage_manager.list_provider_names(),
    }


@app.get("/api/storage/providers")
async def list_provider_storage(force_refresh: bool = False) -> dict:
    summary = await storage_manager.get_summary(force_refresh=force_refresh)
    return {"providers": [provider.model_dump(mode="json") for provider in summary.providers]}


@app.get("/api/storage/summary")
async def get_storage_summary(force_refresh: bool = False) -> dict:
    summary = await storage_manager.get_summary(force_refresh=force_refresh)
    return summary.model_dump(mode="json")


@app.post("/api/storage/refresh")
async def refresh_storage_summary() -> dict:
    summary = await storage_manager.get_summary(force_refresh=True)
    return summary.model_dump(mode="json")


@app.post("/api/storage/reload-config")
async def reload_storage_config() -> dict[str, str | list[str]]:
    storage_manager.reload_provider_configs()
    return {
        "status": "reloaded",
        "providers": storage_manager.list_provider_names(),
    }


@app.get("/api/settings/overview")
async def settings_overview() -> dict:
    try:
        return storage_manager.get_settings_overview()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to load settings overview: {exc}") from exc


@app.post("/api/ai/insights")
async def get_ai_insights() -> dict[str, str]:
    try:
        summary = await storage_manager.get_summary(force_refresh=True)
        insights = await anthropic_service.generate_storage_insights(summary)
        return {"insights": insights}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Anthropic request failed: {exc}") from exc
