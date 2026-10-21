#!/usr/bin/env python3
"""Convert books in a Grimmory library to extra formats, saved next to the original.

Grimmory's library watcher picks up the new file and, in the "auto detect" and
"book per folder" organisation modes, attaches it to the existing book as an
extra format.
"""

import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

PART_SUFFIX = ".grimmory-convert.part"


def log(msg):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}", flush=True)


def env_list(name, default):
    return [f.strip().lower().lstrip(".") for f in os.environ.get(name, default).split(",") if f.strip()]


def env_bool(name, default):
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    library_dir: Path
    source_formats: list
    target_formats: list
    dry_run: bool
    interval_minutes: int
    max_per_run: int
    timeout: int
    state_dir: Path
    ebook_convert: list
    extra_args: list

    @classmethod
    def from_env(cls):
        return cls(
            library_dir=Path(os.environ.get("LIBRARY_DIR", "/books")),
            source_formats=env_list("SOURCE_FORMATS", "epub"),
            target_formats=env_list("TARGET_FORMATS", "azw3"),
            dry_run=env_bool("DRY_RUN", "true"),
            interval_minutes=int(os.environ.get("INTERVAL_MINUTES", "0")),
            max_per_run=int(os.environ.get("MAX_PER_RUN", "0")),
            timeout=int(os.environ.get("CONVERT_TIMEOUT", "600")),
            state_dir=Path(os.environ.get("STATE_DIR", "/config")),
            ebook_convert=shlex.split(os.environ.get("EBOOK_CONVERT", "ebook-convert")),
            extra_args=shlex.split(os.environ.get("EXTRA_ARGS", "")),
        )


def split_ext(name):
    stem, dot, ext = name.rpartition(".")
    return (stem, ext.lower()) if dot and stem else (name, "")


def find_jobs(cfg, failed):
    """Yield (source, target_path, target_format) for every conversion still missing."""
    for dirpath, dirnames, filenames in os.walk(cfg.library_dir):
        # Same convention as Grimmory: a folder with an .ignore file is skipped.
        if ".ignore" in filenames:
            dirnames.clear()
            continue
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))

        present = set()  # (stem lowercased, ext)
        sources = {}  # stem lowercased -> file name of the preferred source
        for name in sorted(filenames):
            if name.startswith(".") or name.endswith(PART_SUFFIX):
                continue
            stem, ext = split_ext(name)
            present.add((stem.lower(), ext))
            if ext in cfg.source_formats:
                current = sources.get(stem.lower())
                if current is None or cfg.source_formats.index(ext) < cfg.source_formats.index(split_ext(current)[1]):
                    sources[stem.lower()] = name

        for key, name in sorted(sources.items()):
            source = Path(dirpath) / name
            stem = split_ext(name)[0]
            for fmt in cfg.target_formats:
                if (key, fmt) in present or failed_key(cfg, source, fmt) in failed:
                    continue
                yield source, source.with_name(f"{stem}.{fmt}"), fmt


def failed_key(cfg, source, fmt):
    return f"{source.relative_to(cfg.library_dir)}::{fmt}"


def load_failed(cfg):
    try:
        return json.loads((cfg.state_dir / "failed.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_failed(cfg, failed):
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    tmp = cfg.state_dir / "failed.json.tmp"
    tmp.write_text(json.dumps(failed, indent=2, sort_keys=True))
    tmp.replace(cfg.state_dir / "failed.json")


def convert(cfg, source, target, fmt):
    """Convert in a scratch dir, then move into the library under a name Grimmory ignores
    and rename it into place, so the watcher only ever sees a complete file."""
    with tempfile.TemporaryDirectory(prefix="grimmory-convert-") as work:
        out = Path(work) / f"out.{fmt}"
        cmd = [*cfg.ebook_convert, str(source), str(out), *cfg.extra_args]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=cfg.timeout)
        if result.returncode != 0 or not out.exists() or out.stat().st_size == 0:
            tail = (result.stderr or result.stdout).strip().splitlines()[-5:]
            raise RuntimeError(f"ebook-convert exited {result.returncode}: " + " | ".join(tail))
        part = target.with_name(target.name + PART_SUFFIX)
        # Never follow a pre-existing part file or symlink: anyone who can write to
        # the library could otherwise redirect this write elsewhere.
        part.unlink(missing_ok=True)
        fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o666)
        with os.fdopen(fd, "wb") as dst, open(out, "rb") as src:
            shutil.copyfileobj(src, dst)
        os.replace(part, target)


def clean_stale_parts(cfg):
    for part in cfg.library_dir.rglob(f"*{PART_SUFFIX}"):
        log(f"Removing leftover {part}")
        part.unlink(missing_ok=True)


def run_once(cfg):
    if not cfg.library_dir.is_dir():
        log(f"Library dir {cfg.library_dir} does not exist")
        return
    clean_stale_parts(cfg)
    failed = load_failed(cfg)
    done = errors = 0
    for source, target, fmt in find_jobs(cfg, failed):
        if cfg.max_per_run and done + errors >= cfg.max_per_run:
            log(f"Reached MAX_PER_RUN={cfg.max_per_run}, rest waits for the next run")
            break
        rel = target.relative_to(cfg.library_dir)
        if cfg.dry_run:
            log(f"[dry-run] would create {rel}")
            done += 1
            continue
        log(f"Converting {source.relative_to(cfg.library_dir)} -> {fmt}")
        started = time.monotonic()
        try:
            convert(cfg, source, target, fmt)
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as e:
            errors += 1
            failed[failed_key(cfg, source, fmt)] = str(e)[:500]
            save_failed(cfg, failed)
            log(f"FAILED {rel}: {e}")
            continue
        done += 1
        log(f"Created {rel} in {time.monotonic() - started:.0f}s")
    verb = "would convert" if cfg.dry_run else "converted"
    log(f"Run finished: {verb} {done}, failed {errors}")


def main():
    # PID 1 in a container ignores SIGTERM unless handled; exiting via SystemExit
    # also makes subprocess.run kill a running ebook-convert.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    os.umask(int(os.environ.get("UMASK", "000"), 8))
    cfg = Config.from_env()
    log(
        f"Library {cfg.library_dir}: {','.join(cfg.source_formats)} -> {','.join(cfg.target_formats)}"
        f"{' (DRY RUN, nothing is written)' if cfg.dry_run else ''}"
    )
    while True:
        run_once(cfg)
        if cfg.interval_minutes <= 0:
            return
        log(f"Next run in {cfg.interval_minutes} min")
        time.sleep(cfg.interval_minutes * 60)


if __name__ == "__main__":
    main()
