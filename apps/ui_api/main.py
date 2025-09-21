
from __future__ import annotations
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pathlib import Path
from typing import List
import asyncio, json

from sdk import SDK_CONFIG

app = FastAPI(title="ConanBot UI API")

def sessions_dir() -> Path:
    return Path(SDK_CONFIG.paths.data_root) / "raw" / "sessions"

@app.get("/sessions")
def list_sessions():
    root = sessions_dir()
    root.mkdir(parents=True, exist_ok=True)
    items = []
    for p in sorted(root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.is_dir():
            items.append({"name": p.name, "path": str(p)})
    return {"sessions": items}

@app.get("/sessions/{name}/events")
def get_events(name: str, limit: int = 200):
    f = sessions_dir() / name / "events.jsonl"
    if not f.exists():
        return JSONResponse(status_code=404, content={"error": "not found"})
    # tail last N lines efficiently
    lines: List[str] = f.read_text(encoding="utf-8").splitlines()[-limit:]
    events = [json.loads(x) for x in lines if x.strip()]
    return {"events": events}

@app.websocket("/ws/sessions/{name}/events")
async def ws_events(ws: WebSocket, name: str):
    await ws.accept()
    f = sessions_dir() / name / "events.jsonl"
    if not f.exists():
        await ws.send_text(json.dumps({"type": "error", "msg": "not found"}))
        await ws.close()
        return
    last_size = f.stat().st_size
    try:
        while True:
            await asyncio.sleep(0.5)
            cur = f.stat().st_size
            if cur > last_size:
                with open(f, "r", encoding="utf-8") as fh:
                    fh.seek(last_size)
                    chunk = fh.read()
                    for line in chunk.splitlines():
                        if line.strip():
                            await ws.send_text(line)
                last_size = cur
    except WebSocketDisconnect:
        return
