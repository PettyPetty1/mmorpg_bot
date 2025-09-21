# tests/unit/test_paths.py
import os
import types
import sys
from pathlib import Path
import pytest

# IMPORTANT:
# These tests assume your file lives at config/paths.py and is importable as `from config.paths import get_paths, Paths`.

def _import_paths_module():
    """
    Import (or re-import) config.paths so we can reset its singleton between tests.
    """
    import importlib
    if "config.paths" in sys.modules:
        return importlib.reload(sys.modules["config.paths"])
    return importlib.import_module("config.paths")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    """
    Keep environment predictable across tests; do not wipe everything because
    system envs may be needed by the runner. We'll set the CONANBOT_* vars inside tests.
    """
    # Ensure we remove any stray fake SDK module between tests
    for key in list(sys.modules.keys()):
        if key == "sdk" or key.startswith("sdk."):
            sys.modules.pop(key, None)
    yield
    for key in list(sys.modules.keys()):
        if key == "sdk" or key.startswith("sdk."):
            sys.modules.pop(key, None)


def test_env_overrides_take_precedence(monkeypatch, tmp_path):
    data = tmp_path / "data_root"
    models = tmp_path / "models_root"
    logs = tmp_path / "logs_root"

    monkeypatch.setenv("CONANBOT_DATA_ROOT", str(data))
    monkeypatch.setenv("CONANBOT_MODELS_ROOT", str(models))
    monkeypatch.setenv("CONANBOT_LOGS_ROOT", str(logs))

    paths_mod = _import_paths_module()
    # Reset singleton to ensure fresh calculation
    paths_mod._paths_singleton = None  # type: ignore[attr-defined]

    p = paths_mod.get_paths(force_refresh=True)

    assert p.data_root == data
    assert p.models_root == models
    assert p.logs_root == logs

    # ensure_all() is called inside get_paths(), so the standard subdirs should exist
    assert (p.sessions_root).is_dir()
    assert (p.processed_root).is_dir()
    # session subdir helper
    demo_sess = p.session_dir("dev_smoke")
    assert demo_sess == data / "raw" / "sessions" / "dev_smoke"


def test_sdk_integration_when_available(monkeypatch, tmp_path):
    """
    Simulate presence of the SDK and ensure paths are derived from SDK_CONFIG.paths.
    We inject a fake `sdk.config` into sys.modules.
    """
    fake_data = tmp_path / "sdk_data"
    fake_models = tmp_path / "sdk_models"
    fake_logs = tmp_path / "sdk_logs"
    # Pre-create to match ensure_all behavior
    for d in (fake_data, fake_models, fake_logs):
        d.mkdir(parents=True, exist_ok=True)

    # Build a fake module tree: sdk.config with SDK_CONFIG.paths fields
    fake_sdk_module = types.ModuleType("sdk")
    fake_config_module = types.ModuleType("sdk.config")

    class _PathsObj:
        data_root = str(fake_data)
        models_root = str(fake_models)
        logs_root = str(fake_logs)

    class _SDKConfig:
        paths = _PathsObj()

    fake_config_module.SDK_CONFIG = _SDKConfig()
    sys.modules["sdk"] = fake_sdk_module
    sys.modules["sdk.config"] = fake_config_module

    paths_mod = _import_paths_module()
    paths_mod._paths_singleton = None  # reset

    p = paths_mod.get_paths(force_refresh=True)

    assert p.data_root == fake_data
    assert p.models_root == fake_models
    assert p.logs_root == fake_logs
    # verify ensure_all created standard subdirs
    assert (p.sessions_root).exists()
    assert (p.logs_training_root).exists()
    assert (p.logs_inference_root).exists()


def test_invalid_data_root_raises_on_ensure(monkeypatch, tmp_path):
    """
    If CONANBOT_DATA_ROOT points to a *file* instead of a directory,
    directory creation should fail during get_paths(force_refresh=True).
    This ensures misconfiguration is surfaced clearly.
    """
    bad_data_file = tmp_path / "not_a_dir.txt"
    bad_data_file.write_text("hi", encoding="utf-8")

    monkeypatch.setenv("CONANBOT_DATA_ROOT", str(bad_data_file))
    monkeypatch.setenv("CONANBOT_MODELS_ROOT", str(tmp_path / "models"))
    monkeypatch.setenv("CONANBOT_LOGS_ROOT", str(tmp_path / "logs"))

    paths_mod = _import_paths_module()
    paths_mod._paths_singleton = None  # reset

    with pytest.raises(Exception):
        # ensure_all() runs inside get_paths(), which should error on making a dir where a file exists
        _ = paths_mod.get_paths(force_refresh=True)


def test_verify_writeable_positive(monkeypatch, tmp_path):
    """
    Sanity check that verify_writeable() passes for normal, writeable directories.
    """
    data = tmp_path / "data"
    models = tmp_path / "models"
    logs = tmp_path / "logs"

    monkeypatch.setenv("CONANBOT_DATA_ROOT", str(data))
    monkeypatch.setenv("CONANBOT_MODELS_ROOT", str(models))
    monkeypatch.setenv("CONANBOT_LOGS_ROOT", str(logs))

    paths_mod = _import_paths_module()
    paths_mod._paths_singleton = None

    p = paths_mod.get_paths(force_refresh=True)
    # Should not raise
    p.verify_writeable()
