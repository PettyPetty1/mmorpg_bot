# .gitignore

The `.gitignore` file specifies files and directories that should **not** be committed to version control.  
This keeps the repository clean and prevents large or machine-specific artifacts from being tracked.

## Excluded categories
- **Virtual environments**: `.venv/`, `env/`
- **Build artifacts**: `__pycache__/`, `*.pyc`
- **Logs & outputs**: `/logs/`, `/data/raw/`, `/data/processed/`
- **Models**: `/models/` (large checkpoints handled outside Git)
- **System files**: `.DS_Store`, `Thumbs.db`

## Purpose
By ignoring these files, we ensure:
- Only source code, configs, and documentation are versioned.
- Large or generated data is kept local or in external storage (S3, datasets).