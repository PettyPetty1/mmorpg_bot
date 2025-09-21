# setup.py

The `setup.py` file defines ConanBot as a Python package.  
It allows installation via `pip install .` and ensures reproducible environments.

## Purpose
- Declares metadata (name, version, author, license).
- Lists install dependencies (mirrors requirements.txt).
- Defines entry points for CLIs (e.g., `recorder_cli`).

## Usage
Install ConanBot locally in editable mode:
```bash
pip install -e .
```

This makes `sdk`, `apps`, and `plugins` importable anywhere in your environment.