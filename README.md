# ConanBot

ConanBot is an SDK-driven scaffold for building a data collection, training, and inference pipeline for games like *Conan Exiles*.  
It includes screen/audio/input recorders, event writers (JSONL, Kafka, S3), PPO reinforcement learning setup, and a FastAPI UI for monitoring.

---

## 📦 Python Dependencies

See [requirements.txt](requirements.txt). Install with:

```bash
pip install -r requirements.txt
```

Key groups:
- **Core SDK:** pydantic, ulid-py
- **Data / Numeric:** numpy, pandas
- **Vision / ML:** torch, torchvision, pillow, opencv-python
- **Audio:** sounddevice, pyaudio
- **OCR:** pytesseract
- **Config:** pyyaml
- **Screen capture:** dxcam, mss, pywin32, psutil
- **Inputs:** inputs, pynput
- **Video muxing:** av, ffmpeg-python
- **UI:** fastapi, uvicorn, websockets, sse-starlette
- **Streaming sinks:** confluent-kafka, boto3, aioboto3, s3fs, smart_open
- **RL / PPO:** stable-baselines3, gymnasium, tensorboard
- **Dev tools:** rich, typer, pytest

---

## 🔧 System Dependencies

- **Tesseract** for OCR  
- **FFmpeg** for video encoding/decoding  
- **Kafka** broker (if KafkaEventWriter used)  
- **AWS CLI/SDK** or credentials for S3 writers  
- **CUDA + NVIDIA drivers** if training on GPU  
- **git-lfs** for large assets

See [EXTERNAL_DEPENDENCIES.md](EXTERNAL_DEPENDENCIES.md).

---

## 🌍 Environment Variables

See [ENV_VARS.md](ENV_VARS.md) for configuration.  
Examples: `CONANBOT_DATA_ROOT`, `CONANBOT_KAFKA_BOOTSTRAP`, `CONANBOT_S3_BUCKET`.

---

## 🚀 Quick Start

1. Install system deps.  
2. Install Python deps:  
   ```bash
   pip install -r requirements.txt
   ```  
3. Run a smoke test recording:  
   ```bash
   python apps/recorder_cli.py --name dev_smoke
   ```  
   → outputs to `data/raw/sessions/dev_smoke/events.jsonl`  
4. Start FastAPI UI:  
   ```bash
   uvicorn apps.ui_api.main:app --reload --port 8000
   ```

---