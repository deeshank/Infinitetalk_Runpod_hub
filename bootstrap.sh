#!/bin/bash
set -e

echo "=== InfiniteTalk RunPod Bootstrap Script ==="

# Configuration
export SERVICE_MODE=api
export SERVER_ADDRESS=127.0.0.1
export HF_HUB_ENABLE_HF_TRANSFER=1

# Base setup
apt-get update -y && apt-get install -y wget git ffmpeg curl
pip install -U "huggingface_hub[hf_transfer]" runpod websocket-client librosa fastapi "uvicorn[standard]"

# Clone and install ComfyUI
if [ ! -d "/ComfyUI" ]; then
  git clone https://github.com/comfyanonymous/ComfyUI.git /ComfyUI
  pip install -r /ComfyUI/requirements.txt
fi

# Custom nodes setup
cd /ComfyUI/custom_nodes

declare -A repos
repos["ComfyUI-Manager"]="https://github.com/Comfy-Org/ComfyUI-Manager.git"
repos["ComfyUI-GGUF"]="https://github.com/city96/ComfyUI-GGUF"
repos["ComfyUI-KJNodes"]="https://github.com/kijai/ComfyUI-KJNodes"
repos["ComfyUI-VideoHelperSuite"]="https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite"
repos["ComfyUI-wanBlockswap"]="https://github.com/orssorbit/ComfyUI-wanBlockswap"
repos["ComfyUI-MelBandRoFormer"]="https://github.com/kijai/ComfyUI-MelBandRoFormer"
repos["ComfyUI-WanVideoWrapper"]="https://github.com/kijai/ComfyUI-WanVideoWrapper"

for node in "${!repos[@]}"; do
  if [ ! -d "$node" ]; then
    git clone "${repos[$node]}" "$node"
    if [ -f "$node/requirements.txt" ]; then
        pip install -r "$node/requirements.txt"
    fi
  fi
done

# Download necessary model weights
mkdir -p /ComfyUI/models/{diffusion_models,loras,vae,text_encoders,clip_vision}
wget -nc https://huggingface.co/Kijai/WanVideo_comfy_GGUF/resolve/main/InfiniteTalk/Wan2_1-InfiniteTalk_Single_Q8.gguf -O /ComfyUI/models/diffusion_models/Wan2_1-InfiniteTalk_Single_Q8.gguf
wget -nc https://huggingface.co/Kijai/WanVideo_comfy_GGUF/resolve/main/InfiniteTalk/Wan2_1-InfiniteTalk_Multi_Q8.gguf -O /ComfyUI/models/diffusion_models/Wan2_1-InfiniteTalk_Multi_Q8.gguf
wget -nc https://huggingface.co/city96/Wan2.1-I2V-14B-480P-gguf/resolve/main/wan2.1-i2v-14b-480p-Q8_0.gguf -O /ComfyUI/models/diffusion_models/wan2.1-i2v-14b-480p-Q8_0.gguf
wget -nc https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors -O /ComfyUI/models/loras/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors
wget -nc https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Wan2_1_VAE_bf16.safetensors -O /ComfyUI/models/vae/Wan2_1_VAE_bf16.safetensors
wget -nc https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/umt5-xxl-enc-bf16.safetensors -O /ComfyUI/models/text_encoders/umt5-xxl-enc-bf16.safetensors
wget -nc https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors -O /ComfyUI/models/clip_vision/clip_vision_h.safetensors
wget -nc https://huggingface.co/Kijai/MelBandRoFormer_comfy/resolve/main/MelBandRoformer_fp16.safetensors -O /ComfyUI/models/diffusion_models/MelBandRoformer_fp16.safetensors

cd /

# Launch entrypoint
chmod +x /root/Infinitetalk_Runpod_hub/entrypoint.sh
/root/Infinitetalk_Runpod_hub/entrypoint.sh
