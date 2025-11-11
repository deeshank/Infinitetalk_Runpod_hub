#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/deeshank/Infinitetalk_Runpod_hub.git}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:/workspace}"
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

COMFY_DIR="${COMFY_DIR:-/ComfyUI}"
INSTALL_CUSTOM_NODES="${INSTALL_CUSTOM_NODES:-0}"
DOWNLOAD_MODELS="${DOWNLOAD_MODELS:-0}"

echo "[bootstrap] Checking ComfyUI..."
if [ ! -f "$COMFY_DIR/main.py" ]; then
  echo "[bootstrap] ComfyUI not found, installing..."
  apt-get update && apt-get install -y git ffmpeg && rm -rf /var/lib/apt/lists/*
  git clone https://github.com/comfyanonymous/ComfyUI.git "$COMFY_DIR"
  cd "$COMFY_DIR"
  pip install -r requirements.txt
  cd -
else
  echo "[bootstrap] ComfyUI already present at $COMFY_DIR"
fi

# ----- GPU Torch + enforced same interpreter for sageattention -----
PY="$(command -v python3 || command -v python)"
PIP="$PY -m pip"

# Detect CUDA flavor or use provided override
TORCH_CUDA="${TORCH_CUDA:-}"
if [ -z "$TORCH_CUDA" ]; then
  if command -v nvidia-smi >/dev/null 2>&1; then
    CUDA_VER=$(nvidia-smi | grep -o "CUDA Version: [0-9]\+\.[0-9]\+" | awk '{print $3}')
  elif [ -f /usr/local/cuda/version.txt ]; then
    CUDA_VER=$(sed -n 's/^CUDA Version \([0-9]\+\.[0-9]\+\).*$/\1/p' /usr/local/cuda/version.txt | head -n1)
  else
    CUDA_VER="12.1"
  fi
  case "$CUDA_VER" in
    12.1*) TORCH_CUDA="cu121" ;;
    12.4*) TORCH_CUDA="cu124" ;;
    12.6*) TORCH_CUDA="cu126" ;;
    12.8*) TORCH_CUDA="cu128" ;;
    *) TORCH_CUDA="cu121" ;;
  esac
fi
echo "[bootstrap] Using Torch CUDA channel: $TORCH_CUDA"

# Install toolchain
apt-get update && apt-get install -y ffmpeg build-essential python3-dev && rm -rf /var/lib/apt/lists/*

# Check if torch already installed
if $PY -c "import torch" &>/dev/null; then
  echo "[bootstrap] Torch already installed: $($PY -c 'import torch;print(torch.__version__, torch.version.cuda)')"
else
  TORCH_VER="${TORCH_VER:-2.4.1}"
  TV_VER="${TV_VER:-0.19.1}"
  TA_VER="${TA_VER:-2.4.1}"
  echo "[bootstrap] Installing GPU PyTorch stack (torch==$TORCH_VER, torchvision==$TV_VER, torchaudio==$TA_VER) ..."
  $PIP install --index-url "https://download.pytorch.org/whl/${TORCH_CUDA}" \
    "torch==${TORCH_VER}" "torchvision==${TV_VER}" "torchaudio==${TA_VER}"
fi

# Verify CUDA availability
$PY - <<'PYCHK'
import torch
print("[bootstrap] Torch version:", torch.__version__)
print("[bootstrap] CUDA version reported by torch:", torch.version.cuda)
assert torch.cuda.is_available(), "ERROR: torch.cuda.is_available() returned False"
print("[bootstrap] CUDA available ✅")
PYCHK

# Install sageattention using same interpreter, no isolation, verbose
echo "[bootstrap] Installing sageattention with no build isolation (same python env)..."
export PIP_NO_BUILD_ISOLATION=1
export PIP_PREFER_BINARY=1
$PIP install --verbose --no-build-isolation --no-cache-dir "sageattention==2.2.0" || {
  echo "[bootstrap] ERROR: sageattention failed to install, showing debug..."
  $PY -m pip debug --verbose
  exit 1
}

# Verify sageattention import prior to ComfyUI startup
$PY - <<'PYCHK2'
import importlib
importlib.import_module("torch")
importlib.import_module("sageattention")
print("[bootstrap] sageattention import OK ✅")
PYCHK2

if [ "$INSTALL_CUSTOM_NODES" = "1" ]; then
  echo "[bootstrap] Installing custom ComfyUI nodes..."
  mkdir -p "$COMFY_DIR/custom_nodes"
  cd "$COMFY_DIR/custom_nodes"
  declare -A repos=(
    ["ComfyUI-Manager"]="https://github.com/Comfy-Org/ComfyUI-Manager.git"
    ["ComfyUI-GGUF"]="https://github.com/city96/ComfyUI-GGUF.git"
    ["ComfyUI-KJNodes"]="https://github.com/kijai/ComfyUI-KJNodes.git"
    ["ComfyUI-VideoHelperSuite"]="https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git"
    ["ComfyUI-wanBlockswap"]="https://github.com/orssorbit/ComfyUI-wanBlockswap.git"
    ["ComfyUI-MelBandRoFormer"]="https://github.com/kijai/ComfyUI-MelBandRoFormer.git"
    ["ComfyUI-WanVideoWrapper"]="https://github.com/kijai/ComfyUI-WanVideoWrapper.git"
  )
  for name in "${!repos[@]}"; do
    if [ ! -d "$name" ]; then
      git clone "${repos[$name]}" "$name"
      if [ -f "$name/requirements.txt" ]; then
        pip install -r "$name/requirements.txt"
      fi
    else
      echo "[bootstrap] Node $name already installed"
    fi
  done
  cd -
fi

if [ "$DOWNLOAD_MODELS" = "1" ]; then
  echo "[bootstrap] Downloading key model files..."
  mkdir -p "$COMFY_DIR/models/diffusion_models" "$COMFY_DIR/models/loras" \
    "$COMFY_DIR/models/vae" "$COMFY_DIR/models/text_encoders" "$COMFY_DIR/models/clip_vision"
  wget -q https://huggingface.co/Kijai/WanVideo_comfy_GGUF/resolve/main/InfiniteTalk/Wan2_1-InfiniteTalk_Single_Q8.gguf -O "$COMFY_DIR/models/diffusion_models/Wan2_1-InfiniteTalk_Single_Q8.gguf"
  wget -q https://huggingface.co/Kijai/WanVideo_comfy_GGUF/resolve/main/InfiniteTalk/Wan2_1-InfiniteTalk_Multi_Q8.gguf -O "$COMFY_DIR/models/diffusion_models/Wan2_1-InfiniteTalk_Multi_Q8.gguf"
  wget -q https://huggingface.co/city96/Wan2.1-I2V-14B-480P-gguf/resolve/main/wan2.1-i2v-14b-480p-Q8_0.gguf -O "$COMFY_DIR/models/diffusion_models/wan2.1-i2v-14b-480p-Q8_0.gguf"
  wget -q https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors -O "$COMFY_DIR/models/loras/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"
  wget -q https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Wan2_1_VAE_bf16.safetensors -O "$COMFY_DIR/models/vae/Wan2_1_VAE_bf16.safetensors"
  wget -q https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/umt5-xxl-enc-bf16.safetensors -O "$COMFY_DIR/models/text_encoders/umt5-xxl-enc-bf16.safetensors"
  wget -q https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors -O "$COMFY_DIR/models/clip_vision/clip_vision_h.safetensors"
  wget -q https://huggingface.co/Kijai/MelBandRoFormer_comfy/resolve/main/MelBandRoformer_fp16.safetensors -O "$COMFY_DIR/models/diffusion_models/MelBandRoformer_fp16.safetensors"
fi

echo "[bootstrap] Starting ComfyUI (if not running) ..."
if ! pgrep -f "$COMFY_DIR/main.py" >/dev/null 2>&1; then
  python "$COMFY_DIR/main.py" --listen --use-sage-attention &
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
