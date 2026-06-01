from __future__ import annotations

import hashlib
import ctypes
import os
import platform
import socket
import sys
from ctypes import Structure, byref, c_ulong, c_ulonglong, sizeof

from agentblaster import __version__
from agentblaster.models import EnvironmentSnapshot


def capture_environment() -> EnvironmentSnapshot:
    """Capture safe reproducibility metadata without storing raw host identifiers."""
    return EnvironmentSnapshot(
        agentblaster_version=__version__,
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        platform_release=platform.release(),
        platform_version=platform.version(),
        os=platform.system(),
        architecture=platform.machine(),
        machine=platform.machine(),
        processor=platform.processor() or None,
        cpu_count=os.cpu_count(),
        memory_total_bytes=memory_total_bytes(),
        ci=_truthy_env("CI") or _truthy_env("GITHUB_ACTIONS"),
        hostname_sha256=_hostname_hash(),
    )


def memory_total_bytes() -> int | None:
    if os.name == "posix":
        try:
            page_size = os.sysconf("SC_PAGE_SIZE")
            page_count = os.sysconf("SC_PHYS_PAGES")
        except (OSError, ValueError, AttributeError):
            return None
        if isinstance(page_size, int) and isinstance(page_count, int):
            return page_size * page_count
        return None

    if os.name == "nt":
        try:
            class MemoryStatusEx(Structure):
                _fields_ = [
                    ("dwLength", c_ulong),
                    ("dwMemoryLoad", c_ulong),
                    ("ullTotalPhys", c_ulonglong),
                    ("ullAvailPhys", c_ulonglong),
                    ("ullTotalPageFile", c_ulonglong),
                    ("ullAvailPageFile", c_ulonglong),
                    ("ullTotalVirtual", c_ulonglong),
                    ("ullAvailVirtual", c_ulonglong),
                    ("ullAvailExtendedVirtual", c_ulonglong),
                ]

            status = MemoryStatusEx()
            status.dwLength = sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(byref(status)):
                return int(status.ullTotalPhys)
        except Exception:
            return None

    return None


def _hostname_hash() -> str | None:
    try:
        hostname = socket.gethostname()
    except OSError:
        return None
    if not hostname:
        return None
    return hashlib.sha256(hostname.encode("utf-8")).hexdigest()


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
