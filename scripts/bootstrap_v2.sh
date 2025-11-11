#!/usr/bin/env bash
set -euo pipefail

# --------------------------------------------------------
# Minimal bootstrap_v2.sh for FastAPI server only (RunPod /workspace version)
# Designed for InfiniteTalk/Multitalk base pods
# --------------------------------------------------------

REPO_URL="${REPO_URL:-https://github.com/deeshank/Infinitetalk_Runpod_hub.git}"
BRANCH="${BRANCH:-dev}"
APP_DIR="${APP_DIR:-/workspace/app}"
PORT="${PORT:-8001}"
SERVER_ADDRESS="${SERVER_ADDRESS:-127.0.0.1}"
RELOAD="${RELOAD:-1}"

echo "[bootstrap_v2] Starting FastAPI bootstrap in /workspace (repo=$REPO_URL, branch=$BRANCH)..."

echo "[bootstrap_v2] Ensuring git, wget, curl..."
if ! command -v git >/dev/null 2>&1; then
  apt-get update && apt-get install -y git curl wget && rm -rf /var/lib/apt/lists/*
fi

PY="$(command -v python3 || command -v python)"
PIP="$PY -m pip"

echo "[bootstrap_v2] Ensuring Python dependencies..."
$PY - <<'PY'
import sys, subprocess
mods_to_pkgs = [
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn[standard]"),
    ("websocket", "websocket-client"),
    ("librosa", "librosa"),
    ("runpod", "runpod"),
    ("huggingface_hub", "huggingface_hub[hf_transfer]"),
]
missing = []
for mod, pkg in mods_to_pkgs:
    try:
        __import__(mod)
    except Exception:
        missing.append(pkg)
if missing:
    print("[bootstrap_v2] Installing deps:", missing)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-U"] + missing)
else:
    print("[bootstrap_v2] FastAPI deps already satisfied")
PY

echo "[bootstrap_v2] Cloning or updating repo into $APP_DIR..."
mkdir -p "$APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch --all --prune
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
else
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi

echo "[bootstrap_v2] Creating symlinks for workflow JSONs and examples..."
ln -sf "$APP_DIR/I2V_single.json" /I2V_single.json || true
ln -sf "$APP_DIR/I2V_multi.json"  /I2V_multi.json  || true
ln -sf "$APP_DIR/V2V_single.json" /V2V_single.json || true
ln -sf "$APP_DIR/V2V_multi.json"  /V2V_multi.json  || true
ln -snf "$APP_DIR/examples"       /workspace/examples || true

echo "[bootstrap_v2] Launching FastAPI server from $APP_DIR ..."
export SERVICE_MODE=api
export SERVER_ADDRESS="$SERVER_ADDRESS"
cd "$APP_DIR"

if [ "$RELOAD" = "1" ]; then
  echo "[bootstrap_v2] Running uvicorn with --reload on port $PORT"
  exec uvicorn api:app --host 0.0.0.0 --port "$PORT" --reload
else
  echo "[bootstrap_v2] Running uvicorn (no reload) on port $PORT"
  exec uvicorn api:app --host 0.0.0.0 --port "$PORT"
fi
