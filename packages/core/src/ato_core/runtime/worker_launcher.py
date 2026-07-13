"""Cross-platform background worker process launcher."""

import json
import os
import subprocess
import sys
from pathlib import Path

_WINDOWS_CREATION_FLAGS = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) | int(
    getattr(subprocess, "DETACHED_PROCESS", 0)
)


class WorkerLauncher:
    """Start an isolated Python worker without shell interpolation."""

    def start(
        self,
        task_root: Path,
        resume: dict[str, object] | None = None,
    ) -> int:
        args = [
            sys.executable,
            "-m",
            "ato_core.runtime.worker",
            "--task-dir",
            str(task_root.resolve()),
        ]
        if resume is not None:
            args.extend(
                ["--resume-json", json.dumps(resume, ensure_ascii=True, separators=(",", ":"))]
            )
        if os.name == "nt":
            process = subprocess.Popen(
                args,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=_WINDOWS_CREATION_FLAGS,
            )
        else:
            process = subprocess.Popen(
                args,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
        return process.pid


def is_process_alive(pid: int) -> bool:
    """Return process liveness without spawning a shell or polling thread."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
