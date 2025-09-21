# config/paths.py
"""
Centralized, cross-platform path management for ConanBot.

Design goals
- Single source of truth for data, models, logs, assets, and temp locations
- Honors these env vars (matching the SDK):
    CONANBOT_DATA_ROOT, CONANBOT_MODELS_ROOT, CONANBOT_LOGS_ROOT
- Sensible OS defaults when env vars are not provided
- Safe directory creation with writeability checks
- Helpers for common subpaths (sessions, processed, models, logs, assets)
- Prefer SDK config if available (sdk.config.SDK_CONFIG.paths)
"""

from __future__ import annotations

import errno
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ---------- OS defaults (used only if env vars not set) ----------

def _platform_default_base() -> Path:
    """
    Returns an OS-specific base directory for user data, following conventions:
    - Windows: %LOCALAPPDATA%/ConanBot
    - macOS:   ~/Library/Application Support/ConanBot
    - Linux:   ~/.local/share/conanbot
    """
    if sys.platform.startswith("win"):
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "ConanBot"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ConanBot"
    else:
        # Linux / other POSIX
        return Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "conanbot"


# ---------- Environment overrides (aligned with SDK) ----------

def _env_or_default_data_root() -> Path:
    return Path(os.getenv("CONANBOT_DATA_ROOT", _platform_default_base() / "data"))


def _env_or_default_models_root() -> Path:
    return Path(os.getenv("CONANBOT_MODELS_ROOT", _platform_default_base() / "models"))


def _env_or_default_logs_root() -> Path:
    return Path(os.getenv("CONANBOT_LOGS_ROOT", _platform_default_base() / "logs"))


# ---------- Repo root detection ----------

def _detect_repo_root(start: Optional[Path] = None) -> Path:
    """
    Best-effort detection of the repository root:
    - Walk upwards from this file to find a directory containing any of:
      .git / pyproject.toml / setup.py / requirements.txt
    - Fallback: two levels up from this file.
    """
    start = (start or Path(__file__)).resolve()
    cur = start.parent
    markers = {".git", "pyproject.toml", "setup.py", "requirements.txt"}
    for _ in range(8):  # avoid infinite climb
        if any((cur / m).exists() for m in markers):
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return Path(__file__).resolve().parents[2]  # project/src layout fallback


# ---------- Core dataclass ----------

@dataclass(frozen=True)
class Paths:
    """
    Canonical path container for ConanBot.

    Most callers should obtain a singleton instance via get_paths().
    """
    repo_root: Path
    data_root: Path
    models_root: Path
    logs_root: Path
    assets_root: Path
    tmp_root: Path

    # ----- factories -----

    @staticmethod
    def from_env_and_repo(repo_root: Optional[Path] = None) -> "Paths":
        rr = _detect_repo_root(repo_root)
        data = _env_or_default_data_root()
        models = _env_or_default_models_root()
        logs = _env_or_default_logs_root()
        # assets default inside repo (adjust if you move assets elsewhere)
        assets = rr / "data" / "assets"
        tmp = rr / ".tmp"
        return Paths(rr, data, models, logs, assets, tmp)

    @staticmethod
    def from_sdk_if_available() -> "Paths":
        """
        If the SDK is importable, derive from its AppConfig.paths.
        Otherwise, fall back to from_env_and_repo().
        """
        try:
            # SDK exports SDK_CONFIG with paths: data_root/models_root/logs_root
            from sdk.config import SDK_CONFIG  # type: ignore
            rr = _detect_repo_root()
            data = Path(SDK_CONFIG.paths.data_root)
            models = Path(SDK_CONFIG.paths.models_root)
            logs = Path(SDK_CONFIG.paths.logs_root)
            assets = rr / "data" / "assets"
            tmp = rr / ".tmp"
            return Paths(rr, data, models, logs, assets, tmp)
        except Exception:
            return Paths.from_env_and_repo()

    # ----- standard layout helpers -----

    @property
    def sessions_root(self) -> Path:
        # SDK Session writes to data_root/raw/sessions/<name>/events.jsonl
        return self.data_root / "raw" / "sessions"

    @property
    def processed_root(self) -> Path:
        return self.data_root / "processed"

    @property
    def models_production_root(self) -> Path:
        return self.data_root / "models" / "production"

    @property
    def logs_training_root(self) -> Path:
        return self.data_root / "logs" / "training"

    @property
    def logs_inference_root(self) -> Path:
        return self.data_root / "logs" / "inference"

    @property
    def logs_system_root(self) -> Path:
        return self.data_root / "logs" / "system"

    # ----- assets helpers -----

    def assets_game_dir(self, game_name: str) -> Path:
        """
        Root assets directory for a specific game, e.g.:
          assets_game_dir("conan_exiles") -> data/assets/conan_exiles
        """
        return self.assets_root / game_name

    def assets_subdir(self, game_name: str, subdir: str) -> Path:
        """
        Convenience for common subfolders, e.g.:
          assets_subdir("conan_exiles", "textures")
          assets_subdir("conan_exiles", "meshes")
        """
        return self.assets_game_dir(game_name) / subdir

    def assets_manifest(self, game_name: str = "conan_exiles") -> Path:
        """
        Canonical location for the per-game assets manifest JSON.
        """
        return self.assets_game_dir(game_name) / "manifest.json"

    def assets_readme(self, game_name: str = "conan_exiles") -> Path:
        """
        Canonical location for the per-game assets README.
        """
        return self.assets_game_dir(game_name) / "README_assets.md"

    # ----- other helpers -----

    def session_dir(self, name: str) -> Path:
        """Return session directory used by recorders/inference runtimes."""
        return self.sessions_root / name

    def processed_split(self, split: str) -> Path:
        """
        Return a processed data split directory (e.g., 'pretrain', 'gameplay', 'validation').
        """
        return self.processed_root / split

    def models_subdir(self, kind: str) -> Path:
        """
        Return a subdirectory for models (e.g., 'encoders', 'policies').
        """
        return self.data_root / "models" / kind

    def logs_area(self, area: str) -> Path:
        """
        Return a logs area: 'training' | 'inference' | 'system' or any custom name.
        """
        return self.data_root / "logs" / area

    # ----- setup / validation -----

    def ensure_all(self) -> None:
        """
        Create common directories used across modules.
        Mirrors the SDK’s ensure() behavior for data_root/models_root/logs_root
        and adds assets/tmp plus standard subfolders.
        """
        for p in [
            self.data_root,
            self.models_root,
            self.logs_root,
            self.assets_root,
            self.tmp_root,
            self.sessions_root,
            self.processed_root,
            self.models_production_root,
            self.logs_training_root,
            self.logs_inference_root,
            self.logs_system_root,
        ]:
            p.mkdir(parents=True, exist_ok=True)

    def verify_writeable(self) -> None:
        """
        Raise OSError if critical roots are not writeable.
        """
        for p in [self.data_root, self.models_root, self.logs_root]:
            try:
                p.mkdir(parents=True, exist_ok=True)
                test = p / ".write_test"
                test.write_text("ok", encoding="utf-8")
                test.unlink(missing_ok=True)
            except Exception as e:
                raise OSError(errno.EACCES, f"Not writeable: {p}", e)


# ---------- Singleton access ----------

_paths_singleton: Optional[Paths] = None

def get_paths(force_refresh: bool = False) -> Paths:
    """
    Return a cached Paths instance (prefers SDK integration when available).
    """
    global _paths_singleton
    if force_refresh or _paths_singleton is None:
        _paths_singleton = Paths.from_sdk_if_available()
        _paths_singleton.ensure_all()
    return _paths_singleton


# ---------- CLI sanity check ----------

if __name__ == "__main__":
    p = get_paths(force_refresh=True)
    try:
        p.verify_writeable()
    except OSError as e:
        print(f"[WARN] Writeability check failed: {e}")

    print("Repo root:          ", p.repo_root)
    print("Data root:          ", p.data_root)
    print("Models root:        ", p.models_root)
    print("Logs root:          ", p.logs_root)
    print("Assets root:        ", p.assets_root)
    print("Tmp root:           ", p.tmp_root)
    print("Sessions root:      ", p.sessions_root)
    print("Processed root:     ", p.processed_root)
    print("Models (prod) root: ", p.models_production_root)
    print("Logs/training root: ", p.logs_training_root)
    print("Logs/inference root:", p.logs_inference_root)
    print("Logs/system root:   ", p.logs_system_root)
    print("Assets manifest:    ", p.assets_manifest())
    print("Assets README:      ", p.assets_readme())
