from fastapi import FastAPI, Request, Query
from fastapi.responses import FileResponse, JSONResponse
import os
import tempfile
import base64
import logging
import uuid
import threading
import time
from inference import run_inference

# In-memory job store
jobs = {}
lock = threading.Lock()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = FastAPI(title="InfiniteTalk API", description="RunPod Pod FastAPI interface for InfiniteTalk", version="1.0")

# Log which inference module is loaded at startup
import inference, sys
logger.info(f"✅ Loaded inference module from: {getattr(inference, '__file__', 'unknown')}")
logger.info(f"Python sys.path = {sys.path}")


@app.get("/health")
def health_check():
    """Simple health check to ensure API and ComfyUI are alive."""
    server_address = os.getenv("SERVER_ADDRESS", "127.0.0.1")
    import urllib.request
    try:
        urllib.request.urlopen(f"http://{server_address}:8188/", timeout=3)
        return {"status": "ok", "comfyui": "connected"}
    except Exception as e:
        logger.warning(f"ComfyUI unreachable: {e}")
        return {"status": "degraded", "error": str(e)}


# Helper: normalized filename and mime detection
import mimetypes

def detect_mime_and_ext(path: str):
    ext = os.path.splitext(path)[1].lower() or ".mp4"
    mime = mimetypes.types_map.get(ext, "video/mp4")
    return ext, mime


# ----------------- Serverless-compatible async endpoints -----------------

def background_job(job_id, body):
    try:
        result = run_inference(body)
        with lock:
            jobs[job_id]["output"] = result
            jobs[job_id]["status"] = "COMPLETED"
            jobs[job_id]["updated_at"] = time.time()
    except Exception as e:
        with lock:
            jobs[job_id]["status"] = "FAILED"
            jobs[job_id]["error"] = str(e)
            jobs[job_id]["updated_at"] = time.time()


@app.post("/run")
def run_async(request_body: dict, output: str = Query("file", enum=["file", "base64", "path"]), preset: str = Query(None)):
    """Async job submission (serverless-compatible schema: {input:{...}})"""
    job_input = request_body.get("input", request_body)
    # fast preset (smaller dimensions to avoid timeout)
    if preset == "fast":
        if "width" not in job_input:
            job_input["width"] = 256
        if "height" not in job_input:
            job_input["height"] = 256
        if "max_frame" not in job_input:
            job_input["max_frame"] = 60
    job_id = str(uuid.uuid4())
    with lock:
        jobs[job_id] = {
            "id": job_id,
            "status": "IN_PROGRESS",
            "input": job_input,
            "output": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
    t = threading.Thread(target=background_job, args=(job_id, job_input))
    t.start()
    return {"id": job_id, "status": "IN_PROGRESS"}


@app.get("/status/{job_id}")
def get_status(job_id: str):
    """Return job status and (if completed) outputs."""
    with lock:
        job = jobs.get(job_id)
        if not job:
            return JSONResponse({"error": "Job not found"}, status_code=404)
        return {
            "id": job_id,
            "status": job["status"],
            "output": job.get("output"),
            "error": job.get("error"),
        }


@app.get("/download/{job_id}")
def download_result(job_id: str):
    """Download the generated file using correct MIME and ext."""
    with lock:
        job = jobs.get(job_id)
        if not job or job["status"] != "COMPLETED":
            return JSONResponse({"error": "Job not ready"}, status_code=404)
        result = job["output"]
    if not result:
        return JSONResponse({"error": "No output"}, status_code=404)

    if "video_path" in result and os.path.exists(result["video_path"]):
        ext, mime = detect_mime_and_ext(result["video_path"])
        fname = os.path.basename(result["video_path"])
        return FileResponse(result["video_path"], media_type=mime, filename=fname)

    if "video" in result:
        decoded = base64.b64decode(result["video"])
        tmp_dir = tempfile.mkdtemp()
        tmp_file = os.path.join(tmp_dir, result.get("filename", "result.mp4"))
        with open(tmp_file, "wb") as f:
            f.write(decoded)
        ext, mime = detect_mime_and_ext(tmp_file)
        return FileResponse(tmp_file, media_type=mime, filename=os.path.basename(tmp_file))

    return JSONResponse({"error": "Output unavailable"}, status_code=500)


@app.post("/runsync")
def run_sync(request_body: dict, output: str = Query("file", enum=["file", "base64", "path"]), preset: str = Query(None)):
    """Blocking call that runs the job synchronously (like serverless /runsync)."""
    job_input = request_body.get("input", request_body)
    if preset == "fast":
        job_input.setdefault("width", 256)
        job_input.setdefault("height", 256)
        job_input.setdefault("max_frame", 60)
    result = run_inference(job_input)
    if "error" in result:
        return JSONResponse(result, status_code=500)
    if "video_path" in result:
        ext, mime = detect_mime_and_ext(result["video_path"])
        return FileResponse(result["video_path"], media_type=mime, filename=os.path.basename(result["video_path"]))
    if "video" in result:
        decoded = base64.b64decode(result["video"])
        tmp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(tmp_dir, result.get("filename", "result.mp4"))
        with open(temp_path, "wb") as f:
            f.write(decoded)
        ext, mime = detect_mime_and_ext(temp_path)
        return FileResponse(temp_path, media_type=mime, filename=os.path.basename(temp_path))
    return JSONResponse({"error": "Unknown result format"}, status_code=500)


# ----------------- Original sync infer (for backward compatibility) -----------------
async def infer(request: Request, output: str = Query("file", enum=["file", "base64", "path"])):
    """Run inference and return output as file, base64 JSON, or path."""
    body = await request.json()
    result = run_inference(body)

    # Error case
    if "error" in result:
        return JSONResponse(content=result, status_code=500)

    if output == "path" and "video_path" in result:
        return JSONResponse(content=result)

    # If base64 video
    if "video" in result:
        if output == "base64":
            return JSONResponse(content=result)
        # Convert base64 to temporary file
        decoded = base64.b64decode(result["video"])
        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, "result.mp4")
        with open(tmp_path, "wb") as f:
            f.write(decoded)
        return FileResponse(tmp_path, media_type="video/mp4", filename="result.mp4")

    # If returning path-based video
    if "video_path" in result and os.path.exists(result["video_path"]):
        return FileResponse(result["video_path"], media_type="video/mp4", filename=os.path.basename(result["video_path"]))

    return JSONResponse(content={"error": "Unknown result format"}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8001"))
    logger.info(f"Starting InfiniteTalk FastAPI server on 0.0.0.0:{port}")
    uvicorn.run("api:app", host="0.0.0.0", port=port)
