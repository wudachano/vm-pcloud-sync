#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vm_pcloud_sync.py
VM ↔ pCloud 同步小工具（呼叫 rclone），支援：
- --mode copy | sync | bisync
- 內建排除規則，可用 --exclude/--include 附加；可用 --no-default-excludes 關閉內建
- --snapshot（只用於 copy/sync）：目的端加時間戳子目錄
- --resync（只用於 bisync 首次建立基準）
- --dry-run, --fast（--fast-list）, --conflict-resolve（bisync）
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime

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
        print(f"❌ 找不到 {exe}，請先安裝（例：sudo apt-get install rclone）", file=sys.stderr)
        sys.exit(2)
    return path

def remote_name_from_dest(dest: str) -> str | None:
    # e.g. "pcloud:TradingHub" -> "pcloud"
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
    ap = argparse.ArgumentParser(description="VM ↔ pCloud 同步工具（rclone 包裝）")
    ap.add_argument("--src", nargs="+", required=True, help="來源資料夾（可多個）")
    ap.add_argument("--dest", required=True, help="目的端（例如 pcloud:TradingHub）")
    ap.add_argument("--mode", choices=["copy", "sync", "bisync"], default="copy", help="copy/sync 單向，bisync 雙向")
    ap.add_argument("--name", default=None, help="目的端固定子目錄名稱（預設用來源資料夾名）")
    ap.add_argument("--snapshot", action="store_true", help="copy/sync 時在目的端加時間戳子目錄（bisync 不適用）")
    ap.add_argument("--dry-run", action="store_true", help="試跑（不真的改動）")
    ap.add_argument("--fast", action="store_true", help="啟用 --fast-list")
    ap.add_argument("--verbose", "-v", action="count", default=1, help="提高輸出詳盡度，可重複，例如 -vv")
    ap.add_argument("--no-default-excludes", action="store_true", help="不要使用內建排除規則")
    ap.add_argument("--exclude", action="append", default=[], help="附加自訂排除規則（可重複）")
    ap.add_argument("--include", action="append", default=[], help="附加自訂包含規則（可重複）")
    # bisync 專用
    ap.add_argument("--resync", action="store_true", help="bisync 首次建立基準（只在第一次執行使用）")
    ap.add_argument("--conflict-resolve", default="newer",
                    choices=["none","newer","older","path1","path2","larger","smaller"],
                    help="bisync 衝突處理策略（預設 newer）")
    args = ap.parse_args()

    rclone = which_or_die("rclone")

    # 快速檢查 remote 可用
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
            print(f"❌ 來源不存在或不是目錄：{src}", file=sys.stderr)
            continue

        # 組目的端路徑
        base = args.name if args.name else src.name
        dest_path = args.dest.rstrip("/")
        if args.mode in ("copy", "sync"):
            if args.snapshot:
                dest_path = f"{dest_path}/{base}-{ts}"
            else:
                dest_path = f"{dest_path}/{base}"
        else:  # bisync：目的端不做 snapshot，rclone 自己管理
            dest_path = f"{dest_path}/{base}"

        # 組排除/包含
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
                cmd.insert(2, "--resync")  # 放在 'bisync' 後面的位置也可

        print(f"\n=== {args.mode.upper()} ===\n來源：{src}\n目的：{dest_path}\n")
        rc = run(cmd)
        if rc == 0:
            print(f"✅ 完成：{src} → {dest_path}\n")
        else:
            print(f"❌ 失敗（返回碼 {rc}）：{src} → {dest_path}\n", file=sys.stderr)

if __name__ == "__main__":
    main()
