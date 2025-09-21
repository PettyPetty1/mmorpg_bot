# sdk/server.py
"""
Server shim that exposes the FastAPI app for uvicorn.
This imports the real app from apps.ui_api.main to provide a stable import path:
    uvicorn sdk.server:app
If you later want startup tasks / shared middleware, add them here.
"""

from importlib import import_module
import os

# Import the app from the real entrypoint.
# Keep this dynamic so you can change the main module path using an env var if needed.
UI_API_MODULE = os.environ.get("CONAN_UI_MODULE", "apps.ui_api.main")

try:
    mod = import_module(UI_API_MODULE)
    # Expect the FastAPI instance to be named `app` in the module.
    app = getattr(mod, "app")
except Exception as exc:
    # Fail fast with a helpful message if import/app is missing.
    raise RuntimeError(
        f"Failed to import FastAPI app from '{UI_API_MODULE}'. "
        "Make sure the module exists and exports `app` (FastAPI instance)."
    ) from exc
