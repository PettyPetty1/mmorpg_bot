
from __future__ import annotations
from pydantic import BaseModel, Field
from pathlib import Path
import os

class Paths(BaseModel):
    repo_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1])
    data_root: Path = Field(default_factory=lambda: Path(os.getenv('CONANBOT_DATA_ROOT', 'data')))
    models_root: Path = Field(default_factory=lambda: Path(os.getenv('CONANBOT_MODELS_ROOT', 'models')))
    logs_root: Path = Field(default_factory=lambda: Path(os.getenv('CONANBOT_LOGS_ROOT', 'logs')))

    def ensure(self) -> None:
        (self.data_root / "raw" / "sessions").mkdir(parents=True, exist_ok=True)
        (self.data_root / "processed").mkdir(parents=True, exist_ok=True)
        self.models_root.mkdir(parents=True, exist_ok=True)
        self.logs_root.mkdir(parents=True, exist_ok=True)

class AppConfig(BaseModel):
    paths: Paths = Field(default_factory=Paths)
    video_fps: int = 30
    timezone: str = "UTC"
    plugins: dict = Field(default_factory=lambda: {
        "screen": "plugins.recorders.screen_stub.impl:ScreenCap",
        "writer.events": "plugins.writers.jsonl.impl:JsonlEventWriter"
    })

SDK_CONFIG = AppConfig()
SDK_CONFIG.paths.ensure()
