#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vm_pcloud_sync.py
Default run (no args):
  src=~/TradingHub  dest=pcloud:TradingHub  mode=copy  (direction: local -> remote)

Options:
  --src ... (multi)      --dest ...        --mode copy|sync|bisync
  --dry-run              --fast            -v / -vv / -vvv
  --no-default-excludes  --exclude PATTERN (repeatable)
  --include PATTERN      --snapshot        --name SUBDIR
  --resync (bisync only) --conflict-resolve newer|older|path1|path2|larger|smaller
  --reverse / --pull     (flip direction: remote -> local)
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
    ap.add_argument("--mode", choices=["copy", "sync", "bisync"], default="copy",
                    help="Default: copy")
    ap.add_argument("--reverse", "--pull", dest="reverse", action="store_true",
                    help="Flip direction: remote -> local (pcloud -> VM).")
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

    multi_src = len(args.src) > 1

    for s in args.src:
        src_local = Path(os.path.expanduser(s)).resolve()

        # In normal (non-reverse) direction, we require local src to exist.
        # In reverse mode (remote -> local), we will create local dest if missing.
        if not args.reverse:
            if not src_local.is_dir():
                print(f"❌ Source not found or not a directory: {src_local}", file=sys.stderr)
                continue
        else:
            # local target dir (dest in reverse) should exist; create if needed
            try:
                src_local.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"❌ Cannot create local target directory: {src_local} ({e})", file=sys.stderr)
                continue

        dest_root = args.dest.rstrip("/")

        # decide a base name for nesting when needed
        if args.name:
            base = args.name
        elif multi_src:
            base = src_local.name
        else:
            base = None  # single source, no forced nesting

        # Build forward (local->remote) and reverse (remote->local) paths
        if not args.reverse:
            # Forward: local src -> remote dest
            forward_src = str(src_local)
            if base:
                forward_dest = f"{dest_root}/{base}"
            else:
                forward_dest = dest_root
            # snapshot applies only to copy/sync
            if args.mode in ("copy", "sync") and args.snapshot:
                forward_dest = f"{Path(forward_dest).as_posix().rstrip('/')}-{ts}"
            real_src, real_dest = forward_src, forward_dest
            direction = "local -> remote"
        else:
            # Reverse: remote src -> local dest
            if base:
                reverse_src_remote = f"{dest_root}/{base}"
            else:
                reverse_src_remote = dest_root
            reverse_dest_local = str(src_local)
            if args.mode in ("copy", "sync") and args.snapshot:
                reverse_dest_local = f"{Path(reverse_dest_local).as_posix().rstrip('/')}-{ts}"
                # ensure snapshot dir exists
                Path(reverse_dest_local).mkdir(parents=True, exist_ok=True)
            real_src, real_dest = reverse_src_remote, reverse_dest_local
            direction = "remote -> local"

        # filters
        fx = build_filter_args(not args.no_default_excludes, args.exclude, args.include)

        # assemble command
        if args.mode in ("copy", "sync"):
            cmd = [rclone, args.mode, real_src, real_dest] + common + fx + ["--create-empty-src-dirs"]
        else:
            # bisync: order matters if using conflict policy path1/path2; reverse flips the order
            path1, path2 = (real_src, real_dest) if not args.reverse else (real_dest, real_src)
            cmd = [rclone, "bisync", path1, path2] + common + fx + [
                "--check-access",
                "--compare", "size,modtime",
                "--create-empty-src-dirs",
                "--resilient",
                "--recover",
                "--conflict-resolve", args.conflict_resolve,
            ]
            if args.resync:
                cmd.insert(2, "--resync")

        print(f"\n=== {args.mode.upper()} ({direction}) ===\nSource : {real_src}\nDest   : {real_dest}\n")
        rc = run(cmd)
        if rc == 0:
            print(f"✅ Done: {real_src} → {real_dest}\n")
        else:
            print(f"❌ Failed (rc={rc}): {real_src} → {real_dest}\n", file=sys.stderr)

if __name__ == "__main__":
    main()

