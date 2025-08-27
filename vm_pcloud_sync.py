#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VM ↔ pCloud sync helper wrapping **rclone**.

Features
--------
- ``--mode copy | sync | bisync``
- Built-in exclude rules (``--no-default-excludes`` to disable) and
  ``--exclude/--include`` for extra patterns
- ``--snapshot`` (copy/sync only) writes to a timestamped subfolder
- ``--resync`` for the first bisync run to create the baseline
- ``--dry-run``, ``--fast`` (``--fast-list``) and ``--conflict-resolve``

Zero-argument defaults:
``--src ~/TradingHub --dest pcloud:TradingHub --mode sync``
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime

DEFAULT_SRC = str(Path.home() / "TradingHub")
DEFAULT_DEST = "pcloud:TradingHub"

DEFAULT_EXCLUDES = [
    "/**/.git/**",
    "/**/.venv/**",
    "/**/venv/**",
    "/**/__pycache__/**",
    "/**/.mypy_cache/**",
    "/**/.pytest_cache/**",
    "/**/*.pyc",
    "/**/*.pyo",
]

def which_or_die(exe: str) -> str:
    path = shutil.which(exe)
    if not path:
        print(f"❌ could not find {exe}; please install it (e.g. sudo apt-get install rclone)", file=sys.stderr)
        sys.exit(2)
    return path

def remote_name_from_dest(dest: str) -> str | None:
    """Extract remote name from ``remote:path`` style strings."""
    if ":" in dest:
        return dest.split(":", 1)[0]
    return None

def run(cmd: list[str]) -> int:
    print("$ " + " ".join(cmd))
    try:
        proc = subprocess.run(cmd)
        return proc.returncode
    except KeyboardInterrupt:
        return 130

def build_exclude_args(default_on: bool, extra_excludes: list[str], extra_includes: list[str]) -> list[str]:
    args: list[str] = []
    patterns = (DEFAULT_EXCLUDES if default_on else []) + (extra_excludes or [])
    for pat in patterns:
        args += ["--exclude", pat]
    for pat in (extra_includes or []):
        args += ["--include", pat]
    return args

def main():
    ap = argparse.ArgumentParser(description="VM ↔ pCloud sync helper (rclone wrapper)")
    ap.add_argument("--src", nargs="+", default=[DEFAULT_SRC], help=f"Source directories (default: {DEFAULT_SRC})")
    ap.add_argument("--dest", default=DEFAULT_DEST, help=f"Destination (default: {DEFAULT_DEST})")
    ap.add_argument("--mode", choices=["copy", "sync", "bisync"], default="sync", help="copy/sync one-way, bisync two-way")
    ap.add_argument("--name", default=None, help="Fixed subdirectory name at destination (defaults to source name)")
    ap.add_argument("--snapshot", action="store_true", help="For copy/sync: append timestamped subdir at destination")
    ap.add_argument("--dry-run", action="store_true", help="Dry run")
    ap.add_argument("--fast", action="store_true", help="Enable --fast-list")
    ap.add_argument("--verbose", "-v", action="count", default=1, help="Increase verbosity; repeat for more output")
    ap.add_argument("--no-default-excludes", action="store_true", help="Disable built-in exclude rules")
    ap.add_argument("--exclude", action="append", default=[], help="Additional exclude patterns (can repeat)")
    ap.add_argument("--include", action="append", default=[], help="Additional include patterns (can repeat)")
    # bisync-specific
    ap.add_argument("--resync", action="store_true", help="First run baseline for bisync")
    ap.add_argument("--conflict-resolve", default="newer",
                    choices=["none","newer","older","path1","path2","larger","smaller"],
                    help="Conflict resolution strategy (bisync)")
    args = ap.parse_args()

    rclone = which_or_die("rclone")

    # quick check that remote is reachable
    remote = remote_name_from_dest(args.dest)
    if remote:
        run([rclone, "about", f"{remote}:"])

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    vflags = ["-v"] * max(1, min(args.verbose, 3))
    common_flags = ["-P", "--stats-one-line", "--stats", "10s"] + vflags
    if args.dry_run:
        common_flags += ["-n"]
    if args.fast:
        common_flags += ["--fast-list"]

    for s in args.src:
        src = Path(os.path.expanduser(s)).resolve()
        if not src.exists() or not src.is_dir():
            print(f"❌ source missing or not a directory: {src}", file=sys.stderr)
            continue

        # destination path
        base = args.name if args.name else src.name
        dest_path = args.dest.rstrip("/")
        if args.mode in ("copy", "sync"):
            if args.snapshot:
                dest_path = f"{dest_path}/{base}-{ts}"
            else:
                dest_path = f"{dest_path}/{base}"
        else:  # bisync manages timestamps itself
            dest_path = f"{dest_path}/{base}"

        # excludes/includes
        fx = build_exclude_args(not args.no_default_excludes, args.exclude, args.include)

        if args.mode in ("copy", "sync"):
            cmd = [rclone, args.mode, str(src), dest_path] + common_flags + fx + ["--create-empty-src-dirs"]
        else:  # bisync
            cmd = [rclone, "bisync", str(src), dest_path] + common_flags + fx + [
                "--check-access",
                "--compare", "size,modtime",
                "--create-empty-src-dirs",
                "--resilient",
                "--recover",
                "--conflict-resolve", args.conflict_resolve,
            ]
            if args.resync:
                cmd.insert(2, "--resync")

        print(f"\n=== {args.mode.upper()} ===\nsource: {src}\ndestination: {dest_path}\n")
        rc = run(cmd)
        if rc == 0:
            print(f"✅ done: {src} → {dest_path}\n")
        else:
            print(f"❌ failed (exit {rc}): {src} → {dest_path}\n", file=sys.stderr)

if __name__ == "__main__":
    main()
