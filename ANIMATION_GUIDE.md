# InfiniteTalk Animation Guide

## Problem: Video only animates for first few seconds

### Root Cause
The `motion_frame` parameter in node 192 controls how many frames have actual animation. The default value of 9 frames means only ~0.36 seconds of animation at 25fps.

### Solution
The code now automatically calculates `motion_frame` based on your video length:
```
motion_frame = max_frame - 72
```

The 72-frame buffer is needed for the InfiniteTalk sliding window algorithm.

## Key Parameters for Animation

### 1. `duration_seconds` (recommended)
Controls total video length. The system calculates everything else:
```python
"duration_seconds": 10  # 10-second video with full animation
```

### 2. `motion_frame` (optional, advanced)
Manually control animation length:
```python
"motion_frame": 259  # For 10s video: (10*25+81) - 72 = 259
```

### 3. `fps` (optional)
Frame rate (default: 25):
```python
"fps": 25  # Standard frame rate
```

## Example Configurations

### Short video (3 seconds)
```python
{
    "duration_seconds": 3,
    "fps": 25
}
# Auto-calculated: max_frame=156, motion_frame=84
```

### Medium video (10 seconds)
```python
{
    "duration_seconds": 10,
    "fps": 25
}
# Auto-calculated: max_frame=331, motion_frame=259
```

### Long video (30 seconds)
```python
{
    "duration_seconds": 30,
    "fps": 25
}
# Auto-calculated: max_frame=831, motion_frame=759
```

## Audio Considerations

- If you provide audio via `wav_url`, `wav_path`, or `wav_base64`, the system can auto-calculate length
- Set `trim_to_audio: true` to match video length to audio length
- Without audio, you MUST specify `duration_seconds` or `max_frame`

## Troubleshooting

### Still getting static video?
1. Check logs for: `Node 192 → motion_frame=X`
2. Ensure motion_frame is close to max_frame (difference should be ~72)
3. Try manually setting: `"motion_frame": <your_max_frame - 72>`

### Video too short?
1. Increase `duration_seconds`
2. Or set `max_frame` directly: `max_frame = fps * duration + 81`

### Poor animation quality?
1. Increase `width` and `height` (but slower generation)
2. Check your prompt - be specific about motion/actions
3. Ensure you're using a good quality input image
