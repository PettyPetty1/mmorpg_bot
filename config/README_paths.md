# config/paths.py

**Purpose**  
Centralized, cross-platform path management for ConanBot. This module defines a single source of truth for data, models, logs, assets, temp folders, and common subpaths (sessions, processed splits, etc.).

**Key features**
- Honors environment overrides: `CONANBOT_DATA_ROOT`, `CONANBOT_MODELS_ROOT`, `CONANBOT_LOGS_ROOT`. (These match the SDK’s config.)  
- Sensible OS defaults:
  - Windows → `%LOCALAPPDATA%/ConanBot/{data,models,logs}`
  - macOS  → `~/Library/Application Support/ConanBot/{data,models,logs}`
  - Linux  → `~/.local/share/conanbot/{data,models,logs}`
- Safe directory creation and writeability checks.
- Optional SDK integration (auto-adopts `sdk.config.SDK_CONFIG.paths` if the SDK is importable).

**Public API**
- `get_paths(force_refresh=False) -> Paths`  
  Returns a cached singleton. Ensures base directories exist.  
- `Paths` (dataclass)
  - **Roots**: `repo_root`, `data_root`, `models_root`, `logs_root`, `assets_root`, `tmp_root`
  - **Common subpaths**:
    - `sessions_root` → `data_root/raw/sessions` (matches SDK Session layout)
    - `processed_root` → `data_root/processed`
    - `models_production_root` → `data_root/models/production`
    - `logs_training_root` / `logs_inference_root` / `logs_system_root`
  - **Helpers**:
    - `session_dir(name)`  
    - `processed_split(split)`  
    - `models_subdir(kind)`  
    - `assets_game_dir(game_name)`  
    - `logs_area(area)`  
  - **Setup/validation**:
    - `ensure_all()` — create common folders
    - `verify_writeable()` — raise if data/models/logs are not writeable

**Interacts with**
- **SDK**: reads the same env vars and (when available) imports `sdk.config.SDK_CONFIG.paths` to stay consistent with `Session` directory layout.  
- **Apps/Plugins**: modules that need to write/read data, models, or logs should call `get_paths()` and derive subpaths instead of hardcoding locations.

**How it interacts**
- When the SDK is present, `Paths.from_sdk_if_available()` uses `SDK_CONFIG.paths` to derive `data_root`, `models_root`, `logs_root`.  
- When the SDK is not present, it falls back to OS defaults or env vars.  
- The `sessions_root` mirrors where the SDK’s `Session` writes event files (`data_root/raw/sessions/<name>/events.jsonl`).

**Inputs / Outputs**
- Inputs: environment variables (`CONANBOT_*`) and optional SDK config.
- Outputs: concrete directories and subpaths on disk; creates folders on demand.

**Extension points**
- Add more helpers for new areas (e.g., `checkpoints_root`, `exports_root`) if the project introduces them.
- If you adopt a YAML config layer later, let it override the env var defaults before constructing `Paths`.

**Notes**
- Call `get_paths()` at the edges of your code (apps, plugins) and pass subpaths inward. This keeps modules testable and avoids implicit globals.
