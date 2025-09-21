#!/usr/bin/env python3
"""
Generate a manifest for game assets.

Outputs:
  1) JSON: detailed stats for tooling
  2) Markdown: pretty summary for README_assets.md

Default root: data/assets/conan_exiles

Examples:
  python tools/scripts/generate_assets_manifest.py
  python tools/scripts/generate_assets_manifest.py --root D:/conan_bot/data/assets/conan_exiles
  python tools/scripts/generate_assets_manifest.py --json out/manifest.json --md out/manifest.md
  python tools/scripts/generate_assets_manifest.py --hash --max-samples 10
"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

# ---------- helpers ----------

def human_bytes(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units) - 1:
        f /= 1024
        i += 1
    return f"{f:.2f} {units[i]}"

def sha256_of_file(p: Path, block: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            h.update(chunk)
    return h.hexdigest()

def ext_key(p: Path) -> str:
    return (p.suffix or "").lower() or "<no extension>"

def rel(root: Path, p: Path) -> str:
    try:
        return str(p.relative_to(root).as_posix())
    except Exception:
        return str(p.as_posix())

# ---------- core scan ----------

def scan_tree(root: Path, do_hash: bool, max_samples: int, ignore_dirs: list[str]) -> dict:
    root = root.resolve()
    total_files = 0
    total_dirs = 0
    total_size = 0

    per_ext = Counter()
    per_ext_size = Counter()
    per_dir_count = defaultdict(int)
    per_dir_size = defaultdict(int)

    largest_files = []  # list of (size, relpath)
    samples = defaultdict(list)  # ext -> [relpaths]
    errors = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored dirs
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
        total_dirs += 1
        dpath = Path(dirpath)

        for name in filenames:
            fpath = dpath / name
            try:
                st = fpath.stat()
                fsize = st.st_size
                total_files += 1
                total_size += fsize

                ek = ext_key(fpath)
                per_ext[ek] += 1
                per_ext_size[ek] += fsize

                parent_rel = rel(root, dpath)
                per_dir_count[parent_rel] += 1
                per_dir_size[parent_rel] += fsize

                # largest N (keep top 100)
                if len(largest_files) < 100:
                    largest_files.append((fsize, rel(root, fpath)))
                    largest_files.sort(reverse=True)
                else:
                    if fsize > largest_files[-1][0]:
                        largest_files[-1] = (fsize, rel(root, fpath))
                        largest_files.sort(reverse=True)

                # collect samples per extension
                if len(samples[ek]) < max_samples:
                    samples[ek].append(rel(root, fpath))

            except Exception as e:
                errors.append({"file": str(fpath), "error": repr(e)})

    # optional hashes for a small, representative set (one per extension + top-10 largest)
    file_hashes = []
    if do_hash:
        # hash one representative per ext
        for ek, paths in samples.items():
            if not paths:
                continue
            p = root / paths[0]
            try:
                file_hashes.append({
                    "category": "by_extension",
                    "extension": ek,
                    "path": rel(root, p),
                    "sha256": sha256_of_file(p)
                })
            except Exception as e:
                errors.append({"file": str(p), "error": repr(e)})
        # hash top-10 largest
        for size, rpath in largest_files[:10]:
            p = root / rpath
            try:
                file_hashes.append({
                    "category": "largest",
                    "path": rpath,
                    "size_bytes": size,
                    "sha256": sha256_of_file(p)
                })
            except Exception as e:
                errors.append({"file": str(p), "error": repr(e)})

    return {
        "root": str(root.as_posix()),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total": {
            "files": total_files,
            "dirs": total_dirs,
            "bytes": total_size,
            "human_size": human_bytes(total_size),
        },
        "by_extension": [
            {
                "extension": ek,
                "files": per_ext[ek],
                "bytes": per_ext_size[ek],
                "human_size": human_bytes(per_ext_size[ek]),
                "samples": samples.get(ek, []),
            }
            for ek in sorted(per_ext.keys(), key=lambda k: per_ext_size[k], reverse=True)
        ],
        "by_directory": [
            {
                "dir": d,
                "files": per_dir_count[d],
                "bytes": per_dir_size[d],
                "human_size": human_bytes(per_dir_size[d]),
            }
            for d in sorted(per_dir_count.keys(), key=lambda k: per_dir_size[k], reverse=True)
        ],
        "largest_files": [
            {"path": p, "bytes": s, "human_size": human_bytes(s)}
            for (s, p) in largest_files[:100]
        ],
        "hashes": file_hashes,
        "errors": errors,
    }

# ---------- markdown rendering ----------

def render_markdown(manifest: dict, top_ext: int, top_dirs: int) -> str:
    lines = []
    lines.append(f"# Conan Exiles Assets Manifest")
    lines.append("")
    lines.append(f"- **Root:** `{manifest['root']}`")
    lines.append(f"- **Generated:** `{manifest['generated_at']}`")
    lines.append(f"- **Total files:** {manifest['total']['files']}")
    lines.append(f"- **Total size:** {manifest['total']['human_size']} ({manifest['total']['bytes']} bytes)")
    lines.append("")

    # Top extensions
    lines.append("## Top extensions")
    lines.append("")
    lines.append("| Extension | Files | Size |")
    lines.append("|---|---:|---:|")
    for row in manifest["by_extension"][:top_ext]:
        lines.append(f"| `{row['extension']}` | {row['files']:,} | {row['human_size']} |")
    lines.append("")

    # Top directories
    lines.append("## Heaviest directories")
    lines.append("")
    lines.append("| Directory | Files | Size |")
    lines.append("|---|---:|---:|")
    for row in manifest["by_directory"][:top_dirs]:
        lines.append(f"| `{row['dir']}` | {row['files']:,} | {row['human_size']} |")
    lines.append("")

    # Largest files
    top_largest = manifest["largest_files"][:20]
    if top_largest:
        lines.append("## Largest files (top 20)")
        lines.append("")
        lines.append("| Path | Size |")
        lines.append("|---|---:|")
        for row in top_largest:
            lines.append(f"| `{row['path']}` | {row['human_size']} |")
        lines.append("")

    # Sample files per extension
    lines.append("## Sample files per extension")
    lines.append("")
    for row in manifest["by_extension"][:top_ext]:
        if not row["samples"]:
            continue
        lines.append(f"**`{row['extension']}`**")
        for s in row["samples"][:5]:
            lines.append(f"- `{s}`")
        lines.append("")

    # Errors
    if manifest["errors"]:
        lines.append("## Errors")
        lines.append("")
        lines.append("> The following files/directories could not be processed:")
        for e in manifest["errors"][:20]:
            lines.append(f"- {e['file']}: `{e['error']}`")
        if len(manifest["errors"]) > 20:
            lines.append(f"- ... {len(manifest['errors']) - 20} more")
        lines.append("")

    return "\n".join(lines)

# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description="Generate assets manifest (JSON + Markdown).")
    ap.add_argument("--root", type=Path, default=Path("data/assets/conan_exiles"), help="Assets root directory.")
    ap.add_argument("--json", type=Path, default=Path("data/assets/conan_exiles_manifest.json"), help="Output JSON path.")
    ap.add_argument("--md", type=Path, default=Path("data/assets/README_assets.md"), help="Output Markdown path.")
    ap.add_argument("--ignore-dirs", nargs="*", default=[".git", ".svn", "__pycache__"], help="Directory names to skip.")
    ap.add_argument("--hash", action="store_true", help="Compute sha256 for representative files (slower).")
    ap.add_argument("--max-samples", type=int, default=5, help="Max sample file paths per extension.")
    ap.add_argument("--top-ext", type=int, default=20, help="How many top extensions to show in Markdown.")
    ap.add_argument("--top-dirs", type=int, default=20, help="How many heaviest dirs to show in Markdown.")
    args = ap.parse_args()

    root = args.root
    if not root.exists():
        raise SystemExit(f"[ERROR] Root does not exist: {root}")

    manifest = scan_tree(root, do_hash=args.hash, max_samples=args.max_samples, ignore_dirs=args.ignore_dirs)

    # Ensure output dirs exist
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.md.parent.mkdir(parents=True, exist_ok=True)

    # write JSON
    with args.json.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # write Markdown
    md = render_markdown(manifest, top_ext=args.top_ext, top_dirs=args.top_dirs)
    with args.md.open("w", encoding="utf-8") as f:
        f.write(md)

    print(f"[OK] JSON   → {args.json}")
    print(f"[OK] README → {args.md}")

if __name__ == "__main__":
    main()
