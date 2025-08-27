#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vm_pcloud_sync.py
Default run (no args):
  src=~/TradingHub  dest=pcloud:TradingHub  mode=sync

Options:
  --src ... (multi)      --dest ...        --mode copy|sync|bisync
  --dry-run              --fast            -v / -vv / -vvv
  --no-default-excludes  --exclude PATTERN (repeatable)
  --include PATTERN      --snapshot        --name SUBDIR
  --resync (bisync only) --conflict-resolve newer|older|path1|path2|larger|smaller
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# Built-in excludes (can be disabled via --no-default-excludes)
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
    p = shutil.which(exe)
    if not p:
        print(f"❌ {exe} not found. Install it first (e.g., `sudo apt-get install rclone`).", file=sys.stderr)
        sys.exit(2)
    return p

def remote_name(dest: str) -> str | None:
    return dest.split(":", 1)[0] if ":" in dest else None

def run(cmd: list[str]) -> int:
    print("$ " + " ".join(cmd))
    try:
        return subprocess.run(cmd).returncode
    except KeyboardInterrupt:
        return 130

def build_filter_args(use_defaults: bool, extra_excludes: list[str], extra_includes: list[str]) -> list[str]:
    args: list[str] = []
    if use_defaults:
        for pat in DEFAULT_EXCLUDES:
            args += ["--exclude", pat]
    for pat in extra_excludes or []:
        args += ["--exclude", pat]
    for pat in extra_includes or []:
        args += ["--include", pat]
    return args

def main():
    ap = argparse.ArgumentParser(description="VM ⇄ pCloud sync via rclone (copy/sync/bisync).")
    # ✅ defaults so running with NO ARGS works as requested
    ap.add_argument("--src", nargs="+", default=[str(Path.home() / "TradingHub")],
                    help="Source directory(ies). Default: ~/TradingHub")
    ap.add_argument("--dest", default="pcloud:TradingHub",
                    help="Destination (remote:path). Default: pcloud:TradingHub")
    ap.add_argument("--mode", choices=["copy", "sync", "bisync"], default="sync",
                    help="Default: sync")
    ap.add_argument("--name", default=None,
                    help="Put under this subfolder on destination (optional).")
    ap.add_argument("--snapshot", action="store_true",
                    help="For copy/sync: write into a timestamped subfolder.")
    ap.add_argument("--dry-run", action="store_true", help="Do not modify, just show actions.")
    ap.add_argument("--fast", action="store_true", help="Use --fast-list.")
    ap.add_argument("--verbose", "-v", action="count", default=1,
                    help="Increase verbosity (-v/-vv/-vvv).")
    ap.add_argument("--no-default-excludes", action="store_true",
                    help="Disable built-in exclude rules.")
    ap.add_argument("--exclude", action="append", default=[],
                    help="Additional exclude pattern (repeatable).")
    ap.add_argument("--include", action="append", default=[],
                    help="Additional include pattern (repeatable).")
    # bisync-only
    ap.add_argument("--resync", action="store_true",
                    help="bisync baseline (use ONCE on first run).")
    ap.add_argument("--conflict-resolve", default="newer",
                    choices=["none","newer","older","path1","path2","larger","smaller"],
                    help="bisync conflict policy. Default: newer")
    args = ap.parse_args()

    rclone = which_or_die("rclone")

    # quick remote sanity check (if dest is a remote)
    rn = remote_name(args.dest)
    if rn:
        run([rclone, "about", f"{rn}:"])

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    vflags = ["-v"] * max(1, min(args.verbose, 3))
    common = ["-P", "--stats-one-line", "--stats", "10s"] + vflags
    if args.dry_run:
        common += ["-n"]
    if args.fast:
        common += ["--fast-list"]

    # decide if we should nest under subfolder on dest:
    # - if --name provided → always nest under that
    # - elif multiple sources → nest by each source's basename
    # - else (single src, no --name) → direct to dest root (matches: rclone * ~/TradingHub pcloud:TradingHub)
    multi_src = len(args.src) > 1

    for s in args.src:
        src = Path(os.path.expanduser(s)).resolve()
        if not src.is_dir():
            print(f"❌ Source not found or not a directory: {src}", file=sys.stderr)
            continue

        # build destination path
        dest_root = args.dest.rstrip("/")
        if args.name:
            base = args.name
            dest_path = f"{dest_root}/{base}"
        elif multi_src:
            base = src.name
            dest_path = f"{dest_root}/{base}"
        else:
            # single source, no name → write directly to dest root
            dest_path = dest_root

        # snapshot only applies to copy/sync (not bisync)
        if args.mode in ("copy", "sync") and args.snapshot:
            snap = f"{Path(dest_path).as_posix().rstrip('/')}-{ts}"
            dest_path = snap

        # filters
        fx = build_filter_args(not args.no_default_excludes, args.exclude, args.include)

        if args.mode in ("copy", "sync"):
            cmd = [rclone, args.mode, str(src), dest_path] + common + fx + ["--create-empty-src-dirs"]
        else:
            cmd = [rclone, "bisync", str(src), dest_path] + common + fx + [
                "--check-access",
                "--compare", "size,modtime",
                "--create-empty-src-dirs",
                "--resilient",
                "--recover",
                "--conflict-resolve", args.conflict_resolve,
            ]
            if args.resync:
                cmd.insert(2, "--resync")

        print(f"\n=== {args.mode.upper()} ===\nSource : {src}\nDest   : {dest_path}\n")
        rc = run(cmd)
        if rc == 0:
            print(f"✅ Done: {src} → {dest_path}\n")
        else:
            print(f"❌ Failed (rc={rc}): {src} → {dest_path}\n", file=sys.stderr)

if __name__ == "__main__":
    main()
