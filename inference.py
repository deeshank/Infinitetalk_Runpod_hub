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
    generate_silent_audio,
)
from handler import client_id as comfy_client_id

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

server_address = os.getenv("SERVER_ADDRESS", "127.0.0.1")

def run_inference(job_input: dict):
    from handler import get_audio_duration  # reuse existing function

    task_id = f"task_{uuid.uuid4()}"
    logger.info(f"🔍 RECEIVED job_input keys: {list(job_input.keys())}")
    logger.info(f"🔍 motion_frame in job_input: {job_input.get('motion_frame')}")
    logger.info(f"🔍 duration_seconds in job_input: {job_input.get('duration_seconds')}")
    
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
    audio_provided = False
    for key in ("wav_path", "wav_url", "wav_base64"):
        if key in job_input:
            wav_path = process_input(job_input[key], task_id, "input_audio.wav", key.split("_")[-1])
            audio_provided = True
            break
    if wav_path is None:
        # No audio provided - check if we should generate silent audio
        duration_seconds = job_input.get("duration_seconds")
        if duration_seconds:
            # Generate silent audio for the requested duration
            os.makedirs(task_id, exist_ok=True)
            silent_audio_path = os.path.join(task_id, "silent_audio.wav")
            wav_path = generate_silent_audio(float(duration_seconds), silent_audio_path)
            if wav_path:
                logger.info(f"🔇 No audio provided - generated {duration_seconds}s silent audio")
            else:
                wav_path = "/examples/audio.mp3"
        else:
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
    
    # Video length and fps controls
    fps = int(job_input.get("fps", 25))
    duration_seconds = job_input.get("duration_seconds")
    max_frame = job_input.get("max_frame")
    
    if duration_seconds:
        max_frame = int(fps * float(duration_seconds)) + 81
        logger.info(f"duration_seconds={duration_seconds}s → fps={fps} → max_frame={max_frame}")
        # Check if audio is long enough
        from handler import get_audio_duration
        audio_duration = get_audio_duration(wav_path)
        if audio_duration and audio_duration < duration_seconds:
            logger.warning(f"⚠️ WARNING: Audio duration ({audio_duration:.2f}s) is shorter than requested video duration ({duration_seconds}s)!")
            logger.warning(f"⚠️ Animation will only be applied for the audio duration, rest may be static.")
    elif max_frame is None:
        logger.info("max_frame not provided, calculating from audio duration")
        from handler import calculate_max_frames_from_audio
        max_frame = calculate_max_frames_from_audio(wav_path, wav_path_2 if person_count == "multi" else None, fps)
    else:
        logger.info(f"Using user-specified max_frame: {max_frame}")
    
    from handler import parse_bool
    trim_to_audio = parse_bool(job_input.get("trim_to_audio", False))

    # Calculate motion_frame: use user input or default to max_frame - 72 (keeps animation throughout)
    motion_frame = job_input.get("motion_frame")
    if motion_frame is None:
        if not audio_provided:
            # When no audio is provided, use more aggressive motion to ensure animation
            motion_frame = max(9, int(max_frame) - 9)
            logger.info(f"🎬 No audio provided - using aggressive motion_frame={motion_frame}")
        else:
            # Default: max_frame - 72 ensures continuous animation (72 is the overlap buffer)
            motion_frame = max(9, int(max_frame) - 72)

    if input_type == "image":
        prompt["284"]["inputs"]["image"] = media_path
    else:
        prompt["228"]["inputs"]["video"] = media_path
    prompt["125"]["inputs"]["audio"] = wav_path
    prompt["241"]["inputs"]["positive_prompt"] = prompt_text
    prompt["245"]["inputs"]["value"] = width
    prompt["246"]["inputs"]["value"] = height
    prompt["270"]["inputs"]["value"] = max_frame
    
    # Update node 192 frame_window_size and motion_frame (critical for video length and animation!)
    if "192" in prompt and "inputs" in prompt["192"]:
        prompt["192"]["inputs"]["frame_window_size"] = int(max_frame)
        prompt["192"]["inputs"]["motion_frame"] = int(motion_frame)
        logger.info(f"✅ Node 192 → frame_window_size={max_frame}, motion_frame={motion_frame}")
    
    # For V2V workflows, override FPS from input video with our specified FPS
    if "194" in prompt:
        prompt["194"]["inputs"]["fps"] = fps
        # If no audio was provided, reduce audio influence
        if not audio_provided:
            prompt["194"]["inputs"]["audio_scale"] = 0.1
            logger.info(f"Node 194 → audio_scale=0.1 (minimizing audio influence)")
        logger.info(f"Node 194 → fps={fps} (overriding input video FPS)")
    
    # Update node 131 video combine settings
    if "131" in prompt:
        prompt["131"]["inputs"]["frame_rate"] = fps
        prompt["131"]["inputs"]["trim_to_audio"] = trim_to_audio
        prompt["131"]["inputs"]["save_output"] = True
        prompt["131"]["inputs"]["format"] = "video/h264-mp4"
        logger.info(f"Node 131 → frame_rate={fps} (overriding input video FPS), trim_to_audio={trim_to_audio}")
    
    # CRITICAL FIX: Node 301 limits output frames based on audio embedding count
    # We need to override it to use max_frame instead
    if "301" in prompt:
        logger.info(f"Node 301 original num_frames: {prompt['301']['inputs'].get('num_frames')}")
        # Override to use node 270 (max_frame) instead of node 194 output
        prompt["301"]["inputs"]["num_frames"] = ["270", 0]
        logger.info(f"✅ Node 301 → num_frames=[270, 0] (using max_frame instead of audio frame count)")
    
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
