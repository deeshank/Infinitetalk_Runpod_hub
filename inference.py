import os
import logging
import websocket
import urllib.request
import base64
import json
import shutil
import time
import uuid
from handler import (
    process_input,
    get_workflow_path,
    load_workflow,
    calculate_max_frames_from_audio,
    get_videos,
    truncate_base64_for_log,
)
from handler import client_id as comfy_client_id

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

server_address = os.getenv("SERVER_ADDRESS", "127.0.0.1")

def run_inference(job_input: dict):
    from handler import get_audio_duration  # reuse existing function

    task_id = f"task_{uuid.uuid4()}"
    input_type = job_input.get("input_type", "image")
    person_count = job_input.get("person_count", "single")

    workflow_path = get_workflow_path(input_type, person_count)
    logger.info(f"Workflow: {workflow_path}, type={input_type}, persons={person_count}")

    media_path = None
    if input_type == "image":
        for key in ("image_path", "image_url", "image_base64"):
            if key in job_input:
                media_path = process_input(job_input[key], task_id, "input_image.jpg", key.split("_")[-1])
                break
        if media_path is None:
            media_path = "/examples/image.jpg"
    else:
        for key in ("video_path", "video_url", "video_base64"):
            if key in job_input:
                media_path = process_input(job_input[key], task_id, "input_video.mp4", key.split("_")[-1])
                break
        if media_path is None:
            media_path = "/examples/image.jpg"

    wav_path = None
    wav_path_2 = None
    for key in ("wav_path", "wav_url", "wav_base64"):
        if key in job_input:
            wav_path = process_input(job_input[key], task_id, "input_audio.wav", key.split("_")[-1])
            break
    if wav_path is None:
        wav_path = "/examples/audio.mp3"
    if person_count == "multi":
        for key in ("wav_path_2", "wav_url_2", "wav_base64_2"):
            if key in job_input:
                wav_path_2 = process_input(job_input[key], task_id, "input_audio_2.wav", key.split("_")[-1])
                break
        if wav_path_2 is None:
            wav_path_2 = wav_path

    prompt = load_workflow(workflow_path)
    prompt_text = job_input.get("prompt", "A person talking naturally")
    width = job_input.get("width", 512)
    height = job_input.get("height", 512)
    max_frame = job_input.get("max_frame")
    if max_frame is None:
        max_frame = calculate_max_frames_from_audio(wav_path, wav_path_2 if person_count == "multi" else None)

    if input_type == "image":
        prompt["284"]["inputs"]["image"] = media_path
    else:
        prompt["228"]["inputs"]["video"] = media_path
    prompt["125"]["inputs"]["audio"] = wav_path
    prompt["241"]["inputs"]["positive_prompt"] = prompt_text
    prompt["245"]["inputs"]["value"] = width
    prompt["246"]["inputs"]["value"] = height
    prompt["270"]["inputs"]["value"] = max_frame
    if person_count == "multi":
        if input_type == "image" and "307" in prompt:
            prompt["307"]["inputs"]["audio"] = wav_path_2
        elif input_type == "video" and "313" in prompt:
            prompt["313"]["inputs"]["audio"] = wav_path_2

    http_url = f"http://{server_address}:8188/"
    for attempt in range(60):
        try:
            urllib.request.urlopen(http_url, timeout=5)
            logger.info(f"ComfyUI ready after {attempt}s")
            break
        except Exception:
            time.sleep(1)

    ws_url = f"ws://{server_address}:8188/ws?clientId={comfy_client_id}"
    ws = websocket.WebSocket()
    for _ in range(5):
        try:
            ws.connect(ws_url)
            break
        except Exception as e:
            logger.warning(f"WebSocket connect failed: {e}")
            time.sleep(2)

    videos = get_videos(ws, prompt, input_type, person_count)
    ws.close()

    output_video_path = None
    for node_id, vidlist in videos.items():
        if vidlist:
            output_video_path = vidlist[0]
            break
    if not output_video_path or not os.path.exists(output_video_path):
        return {"error": "No output video found"}

    if job_input.get("network_volume"):
        out_path = f"/runpod-volume/infinitetalk_{task_id}.mp4"
        os.makedirs("/runpod-volume", exist_ok=True)
        shutil.copy2(output_video_path, out_path)
        return {"video_path": out_path}
    else:
        with open(output_video_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        logger.info(f"Returning base64 video: {truncate_base64_for_log(b64)}")
        return {"video": b64}
