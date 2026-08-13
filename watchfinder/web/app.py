from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from watchfinder.config import load_config
from watchfinder.pipeline import run_scan

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

app = FastAPI(title="WatchFinder", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

_last_result = None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    cfg = load_config()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "result": _last_result,
            "default_queries": "\n".join(cfg.queries),
            "errors": (_last_result.errors if _last_result else []),
            "sources": {
                "hibid": cfg.sources.hibid,
                "catawiki": cfg.sources.catawiki,
                "liveauctioneers": cfg.sources.liveauctioneers,
            },
        },
    )


@app.post("/scan", response_class=HTMLResponse)
async def scan(
    request: Request,
    queries: str = Form(""),
    include_hibid: str | None = Form(None),
    include_catawiki: str | None = Form(None),
    include_liveauctioneers: str | None = Form(None),
) -> HTMLResponse:
    global _last_result
    cfg = load_config()
    query_list = [q.strip() for q in queries.splitlines() if q.strip()]
    if not query_list:
        query_list = cfg.queries
    cfg.sources.hibid = include_hibid is not None
    cfg.sources.catawiki = include_catawiki is not None
    cfg.sources.liveauctioneers = include_liveauctioneers is not None
    cfg.max_lots_per_source = min(cfg.max_lots_per_source, 20)
    _last_result = run_scan(cfg, queries=query_list)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "result": _last_result,
            "default_queries": "\n".join(query_list),
            "errors": _last_result.errors,
            "sources": {
                "hibid": cfg.sources.hibid,
                "catawiki": cfg.sources.catawiki,
                "liveauctioneers": cfg.sources.liveauctioneers,
            },
        },
    )


@app.get("/api/last")
async def api_last() -> JSONResponse:
    if _last_result is None:
        return JSONResponse({"error": "No scan yet"}, status_code=404)
    return JSONResponse(json.loads(_last_result.model_dump_json()))
