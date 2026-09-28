import os
import json
import asyncio
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app.config import settings
from app.browser_manager import browser_manager
from app.database import init_db, get_history, get_query_by_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("bestresponse")

# Initialize database
init_db()

app = FastAPI(title=settings.app_name)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

class QueryRequest(BaseModel):
    prompt: str
    models: List[str] = ["ChatGPT", "Claude", "Gemini", "GLM"]
    judge_model: str = "Gemini"
    headless: bool = False

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.get("/")
async def get_index():
    index_file = STATIC_DIR / "index.html"
    return FileResponse(str(index_file))

@app.post("/api/login/open")
async def open_login():
    res = await browser_manager.open_login_window()
    return JSONResponse(res)

@app.post("/api/login/close")
async def close_login():
    res = await browser_manager.close_login_window()
    return JSONResponse(res)

@app.get("/api/login/status")
async def get_login_status():
    status = await browser_manager.check_all_logins()
    return JSONResponse(status)

@app.get("/api/history")
async def fetch_history(limit: int = 20):
    return JSONResponse(get_history(limit=limit))

@app.get("/api/history/{query_id}")
async def fetch_query_detail(query_id: int):
    item = get_query_by_id(query_id)
    if not item:
        raise HTTPException(status_code=404, detail="Query record not found")
    return JSONResponse(item)

@app.post("/api/query")
async def execute_query(req: QueryRequest):
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")
    
    result = await browser_manager.run_multi_query(
        prompt=req.prompt.strip(),
        selected_models=req.models,
        judge_model_choice=req.judge_model,
        headless=req.headless
    )
    return JSONResponse(result)

@app.websocket("/ws/query")
async def websocket_query_endpoint(websocket: WebSocket):
    await websocket.accept()
    progress_queue: asyncio.Queue = asyncio.Queue()
    queue_stop_event = asyncio.Event()

    async def queue_worker():
        """Reads progress messages from the queue and sends them sequentially."""
        try:
            while not queue_stop_event.is_set():
                try:
                    item = await asyncio.wait_for(progress_queue.get(), timeout=0.2)
                    if item is None:
                        break
                    await websocket.send_json(item)
                    progress_queue.task_done()
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break
        except Exception as e:
            logger.debug(f"Queue worker ended: {e}")

    worker_task = asyncio.create_task(queue_worker())

    try:
        data = await websocket.receive_json()
        prompt = data.get("prompt", "").strip()
        models = data.get("models", ["ChatGPT", "Claude", "Gemini", "GLM"])
        judge = data.get("judge", "Gemini")
        headless = data.get("headless", False)

        if not prompt:
            await websocket.send_json({"type": "error", "message": "Prompt cannot be empty"})
            return

        def on_progress(source: str, message: str):
            try:
                progress_queue.put_nowait({
                    "type": "progress",
                    "source": source,
                    "message": message
                })
            except Exception as e:
                logger.debug(f"Progress queue error: {e}")

        result = await browser_manager.run_multi_query(
            prompt=prompt,
            selected_models=models,
            judge_model_choice=judge,
            headless=headless,
            progress_callback=on_progress
        )

        # Wait briefly for queue to flush
        await asyncio.sleep(0.3)
        await websocket.send_json({
            "type": "complete",
            "data": result
        })

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except Exception as e:
        logger.error(f"WebSocket execution error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        queue_stop_event.set()
        await progress_queue.put(None)
        worker_task.cancel()
        try:
            await websocket.close()
        except Exception:
            pass
