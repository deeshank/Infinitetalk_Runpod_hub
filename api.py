from fastapi import FastAPI, Request, Query
from fastapi.responses import FileResponse, JSONResponse
import os
import tempfile
import base64
import logging
from inference import run_inference

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = FastAPI(title="InfiniteTalk API", description="RunPod Pod FastAPI interface for InfiniteTalk", version="1.0")


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


@app.post("/infer")
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
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"Starting InfiniteTalk FastAPI server on 0.0.0.0:{port}")
    uvicorn.run("api:app", host="0.0.0.0", port=port)
