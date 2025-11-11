#!/usr/bin/env python3
import time
import sys
import requests

BASE_URL = "https://u84vw2s5g9q7rs-8001.proxy.runpod.net"

def submit_job(image_url: str, prompt: str, preset="fast"):
    payload = {
        "input": {
            "input_type": "image",
            "person_count": "single",
            "image_url": image_url,
            "prompt": prompt,
            "width": 512,
            "height": 512,
            "duration_seconds": 10,
            "fps": 25,
            "trim_to_audio": "false",
            # motion_frame controls animation length - will auto-calculate if not provided
            # For 10 seconds at 25fps: max_frame = 331, motion_frame should be ~259 (331-72)
            # "motion_frame": 259,  # Uncomment to manually control animation length
            
            # Add your audio file here - example:
            # "wav_url": "https://your-audio-url.com/audio.wav"
            # OR use a local path if running in container:
            # "wav_path": "/path/to/your/audio.wav"
        }
    }
    # resp = requests.post(f"{BASE_URL}/run", params={"preset": preset}, json=payload)
    resp = requests.post(f"{BASE_URL}/run", json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to start job: {resp.text}")
    job = resp.json()
    print(f"🚀 Job started: {job}")
    return job["id"]

def wait_for_completion(job_id: str, poll_interval=10):
    print(f"⏳ Waiting for job {job_id} to complete...")
    while True:
        resp = requests.get(f"{BASE_URL}/status/{job_id}")
        if resp.status_code != 200:
            print(f"Error polling status: {resp.text}")
            break
        data = resp.json()
        status = data.get("status")
        if status == "COMPLETED":
            print("✅ Job completed successfully!")
            return True
        elif status == "FAILED":
            print(f"❌ Job failed: {data.get('error')}")
            return False
        else:
            print(f"Status: {status} - waiting...")
            time.sleep(poll_interval)

def download_result(job_id: str):
    output_file = f"{job_id}.mp4"
    print(f"⬇️  Downloading result for job {job_id} ...")
    with requests.get(f"{BASE_URL}/download/{job_id}", stream=True) as r:
        if r.status_code != 200:
            raise RuntimeError(f"Download failed: {r.text}")
        with open(output_file, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    print(f"🎥 Saved output video as {output_file}")

def main():
    # if len(sys.argv) < 3:
    #     print("Usage: python scripts/runpod_autorun.py <image_url> <prompt>")
    #     sys.exit(1)

    # image_url = sys.argv[1]
    # prompt = " ".join(sys.argv[2:])
    
    image_url = "https://i.postimg.cc/nVjhn2vL/pexels-ailin-policano-2150264477-34611213.jpg"
    prompt = """
A sensual young woman with luscious full lips is posed intimately in a softly-lit boudoir, inspired by [reference image]. She gently smiles, parts her lips, and speaks softly, occasionally blinking and turning her head slightly. Her elegant hair cascades over bare shoulders, and her eyes glimmer invitingly. The scene is cinematic and intimate, focusing on close-up facial features and natural expressions. Style: ultra-realistic, highly detailed, tasteful, HD resolution, bokeh background.
"""

    try:
        job_id = submit_job(image_url, prompt)
        if wait_for_completion(job_id):
            download_result(job_id)
        else:
            print("Job did not complete successfully.")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
