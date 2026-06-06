"""
zhclip Web 界面 — FastAPI

启动:
    uvicorn web.app:app --host 0.0.0.0 --port 8080
"""

import os
import sys
import json
import time
import uuid
import logging
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from zhclip.transcribe import transcribe_file, transcribe_url, DATA_DIR, TEMP_DIR

logger = logging.getLogger("zhclip.web")

app = FastAPI(title="zhclip", version="0.1.0")

# 上传目录（使用共享数据目录）
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class URLTranscribeRequest(BaseModel):
    url: str
    language: str = "auto"
    translate: bool = False


@app.get("/", response_class=HTMLResponse)
async def index():
    template_path = Path(__file__).parent / "templates" / "index.html"
    content = template_path.read_text(encoding="utf-8")
    from fastapi.responses import HTMLResponse as Resp
    import time
    return Resp(content=content, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
        "ETag": str(int(time.time())),
    })


@app.get("/test")
async def test():
    template_path = Path(__file__).parent / "templates" / "test.html"
    return HTMLResponse(template_path.read_text(encoding="utf-8"))


@app.post("/api/transcribe/file")
async def transcribe_file_api(
    file: UploadFile = File(...),
    language: str = Form("auto"),
    translate: bool = Form(False),
):
    """上传文件并转写"""
    ext = os.path.splitext(file.filename or "audio.mp3")[1] or ".mp3"
    save_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"

    content = await file.read()
    save_path.write_bytes(content)

    file_size_mb = len(content) / 1024 / 1024
    logger.info(f"收到文件: {file.filename} ({file_size_mb:.1f}MB)")

    if file_size_mb > 500:
        save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail="文件超过 500MB 限制")

    try:
        result = transcribe_file(str(save_path), language=language, translate=translate)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        save_path.unlink(missing_ok=True)


@app.post("/api/transcribe/url")
async def transcribe_url_api(req: URLTranscribeRequest):
    """下载 URL 视频并转写"""
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="URL 不能为空")

    logger.info(f"收到 URL 转写请求: {req.url[:80]}...")
    print(f"[DEBUG] transcribe_url_api called: {req.url[:60]}...", flush=True)

    try:
        result = transcribe_url(req.url, language=req.language, translate=req.translate)
        print(f"[DEBUG] transcribe_url_api done: {len(result.get('segments',[]))} segs", flush=True)
        return result
    except Exception as e:
        print(f"[DEBUG] transcribe_url_api error: {e}", flush=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "转写失败",
                "detail": str(e)[:300],
                "text": "",
            }
        )


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


def main():
    """直接运行: python -m web.app"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print("""
╔══════════════════════════════════╗
║         zhclip Web               ║
║  纯 CPU 中文视频转文字            ║
╚══════════════════════════════════╝
""")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info",
                timeout_keep_alive=300)


if __name__ == "__main__":
    main()