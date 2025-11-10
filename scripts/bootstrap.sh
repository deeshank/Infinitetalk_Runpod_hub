#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/deeshank/Infinitetalk_Runpod_hub.git}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/runpod-volume/app}"
PORT="${PORT:-8000}"
SERVER_ADDRESS="${SERVER_ADDRESS:-127.0.0.1}"
RELOAD="${RELOAD:-1}"

echo "[bootstrap] Ensuring tools..."
if ! command -v git >/dev/null 2>&1; then
  apt-get update && apt-get install -y git curl wget && rm -rf /var/lib/apt/lists/*
fi

echo "[bootstrap] Ensuring Python deps (most are preinstalled by image)..."
python - <<'PY'
import importlib, sys
missing = []
for pkg in ["fastapi","uvicorn","websocket","librosa","runpod","huggingface_hub"]:
    try: importlib.import_module(pkg)
    except Exception: missing.append(pkg)
if missing:
    print("[bootstrap] Installing:", missing)
    import subprocess; subprocess.check_call([sys.executable,"-m","pip","install","-U","uvicorn[standard]","fastapi","websocket-client","librosa","runpod","huggingface_hub[hf_transfer]"])
else:
    print("[bootstrap] Python deps OK")
PY

echo "[bootstrap] Cloning/updating repo at $APP_DIR ..."
mkdir -p "$APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch --all --prune
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
else
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi

echo "[bootstrap] Creating symlinks for workflow files and examples ..."
ln -sf "$APP_DIR/I2V_single.json" /I2V_single.json || true
ln -sf "$APP_DIR/I2V_multi.json"  /I2V_multi.json  || true
ln -sf "$APP_DIR/V2V_single.json" /V2V_single.json || true
ln -sf "$APP_DIR/V2V_multi.json"  /V2V_multi.json  || true
ln -snf "$APP_DIR/examples"       /examples        || true

echo "[bootstrap] Starting ComfyUI (if not running) ..."
if ! pgrep -f "/ComfyUI/main.py" >/dev/null 2>&1; then
  python /ComfyUI/main.py --listen --use-sage-attention &
fi

echo "[bootstrap] Waiting for ComfyUI to be ready ..."
for i in $(seq 1 120); do
  if curl -s "http://127.0.0.1:8188/" >/dev/null 2>&1; then
    echo "[bootstrap] ComfyUI is ready"
    break
  fi
  sleep 1
done

echo "[bootstrap] Launching API from $APP_DIR ..."
export SERVICE_MODE=api
export SERVER_ADDRESS="$SERVER_ADDRESS"
cd "$APP_DIR"

if [ "$RELOAD" = "1" ]; then
  echo "[bootstrap] Running uvicorn with --reload on port $PORT"
  exec uvicorn api:app --host 0.0.0.0 --port "$PORT" --reload
else
  echo "[bootstrap] Running uvicorn (no reload) on port $PORT"
  exec uvicorn api:app --host 0.0.0.0 --port "$PORT"
fi
