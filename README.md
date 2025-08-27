# vm-pcloud-sync

VM ⇄ pCloud sync via **rclone** (`copy`/`sync`/`bisync`).  
Single-file Python wrapper with **built-in exclude rules** and CLI options for extra includes/excludes.

> **Zero-argument default:**  
> Just run `python3 vm_pcloud_sync.py`  
> = `--src ~/TradingHub --dest pcloud:TradingHub --mode sync`

## Features
- `copy` / `sync` (one-way) and `bisync` (two-way)
- Built-in excludes: `.git/`, `.venv/`, `__pycache__/`, `*.pyc` …  
  (disable via `--no-default-excludes`; extend with `--exclude/--include`)
- `--resync` for the **first** bisync run (baseline)
- Optional `--snapshot` (for copy/sync) to write into a timestamped subfolder
- Works well with **systemd user timers** on Linux VMs
- Verbosity control (`-v/-vv/-vvv`), `--fast-list`, `--dry-run`

## Prerequisites
- Linux VM (e.g., Ubuntu/Debian)
- rclone ≥ 1.62  
  ```bash
  sudo apt-get update && sudo apt-get install -y rclone
  rclone version
  ```
* A configured pCloud remote (assumed name: `pcloud:`)

  ```bash
  rclone config
  rclone about pcloud:
  ```

## Quick Start

### 0) Zero-argument default

```bash
python3 vm_pcloud_sync.py
# == --src ~/TradingHub --dest pcloud:TradingHub --mode sync
```

### 1) One-way backup (copy)

```bash
python3 vm_pcloud_sync.py --src ~/TradingHub --dest pcloud:TradingHub --mode copy
```

### 2) One-way mirror (sync)

```bash
python3 vm_pcloud_sync.py --src ~/TradingHub --dest pcloud:TradingHub --mode sync -n   # dry-run
python3 vm_pcloud_sync.py --src ~/TradingHub --dest pcloud:TradingHub --mode sync
```

### 3) Two-way sync (bisync)

**First run (baseline):**

```bash
python3 vm_pcloud_sync.py --src ~/TradingHub --dest pcloud:TradingHub --mode bisync --resync
```

**Daily run:**

```bash
python3 vm_pcloud_sync.py --src ~/TradingHub --dest pcloud:TradingHub --mode bisync
```

**Add your own rules:**

```bash
python3 vm_pcloud_sync.py --mode bisync \
  --src ~/TradingHub --dest pcloud:TradingHub \
  --exclude "/**/logs/**" --include "/**/*.csv"
```

## CLI summary

* `--src ...` (multi) | `--dest ...` (remote:path) | `--mode copy|sync|bisync`
* `--dry-run` | `--fast` | `-v/-vv/-vvv`
* `--no-default-excludes` | `--exclude PATTERN` | `--include PATTERN`
* `--snapshot` (copy/sync only) | `--name SUBDIR`
* `--resync` (bisync only) | `--conflict-resolve newer|older|path1|path2|larger|smaller`

## Systemd (optional)

Create user service & timer for periodic bisync (edit paths as needed).

`~/.config/systemd/user/vm-pcloud-sync.service`

```ini
[Unit]
Description=VM <-> pCloud sync (bisync)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /home/<USER>/vm_pcloud_sync.py \
  --mode bisync --src /home/<USER>/TradingHub --dest pcloud:TradingHub
```

`~/.config/systemd/user/vm-pcloud-sync.timer`

```ini
[Unit]
Description=Run vm-pcloud-sync every 15 minutes

[Timer]
OnBootSec=2m
OnUnitActiveSec=15m
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:

```bash
systemctl --user daemon-reload
systemctl --user enable --now vm-pcloud-sync.timer
```

## Notes

* Use `--resync` **once** on the first `bisync` to establish the baseline.
* If multiple machines sync the same path, **stagger** their timers to avoid concurrent operations.
* Built-in excludes can be disabled with `--no-default-excludes`.

## License

MIT

