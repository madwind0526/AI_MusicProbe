"""Host resource monitoring for the application header."""

from __future__ import annotations

import subprocess

import psutil


def resource_snapshot() -> dict:
    memory = psutil.virtual_memory()
    payload = {
        "cpu": {"percent": round(psutil.cpu_percent(interval=None), 1)},
        "memory": {
            "percent": round(memory.percent, 1),
            "usedGiB": round(memory.used / (1024**3), 1),
            "totalGiB": round(memory.total / (1024**3), 1),
        },
        "gpu": None,
    }
    try:
        process = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        first = process.stdout.strip().splitlines()[0]
        name, usage, used, total = [part.strip() for part in first.split(",", 3)]
        payload["gpu"] = {
            "name": name,
            "percent": float(usage),
            "usedMiB": float(used),
            "totalMiB": float(total),
        }
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        pass
    return payload
