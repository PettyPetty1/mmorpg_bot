# requirements.txt

This file lists all Python dependencies for ConanBot.

## Groups of dependencies
- **Core SDK** — pydantic, ulid-py
- **Numerics** — numpy, pandas
- **ML / Vision** — torch, torchvision, pillow, opencv-python
- **Audio** — sounddevice, pyaudio
- **OCR** — pytesseract (requires system Tesseract binary)
- **Screen capture** — dxcam (Windows), mss, pywin32
- **Inputs** — inputs, pynput
- **Video** — av, ffmpeg-python (requires system ffmpeg)
- **UI** — fastapi, uvicorn, websockets, sse-starlette
- **Streaming sinks** — confluent-kafka, boto3, aioboto3, s3fs, smart_open
- **RL** — stable-baselines3 (PPO), gymnasium, tensorboard
- **Dev tools** — rich, typer, pytest

## Installation
```bash
pip install -r requirements.txt
```

For GPU builds, see PyTorch’s install guide.