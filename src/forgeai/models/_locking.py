"""Verrouillage fichier inter-process et inter-thread."""

import fcntl
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def file_lock(path: Path):
    """Context manager de verrou exclusif sur un fichier .lock associé à `path`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = str(path) + ".lock"
    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        fd.close()
