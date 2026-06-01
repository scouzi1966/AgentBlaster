from __future__ import annotations

import hashlib
import ctypes
from importlib.util import find_spec
import json
import os
import platform
import socket
import sys
from pathlib import Path
from ctypes import Structure, byref, c_ulong, c_ulonglong, sizeof
from typing import Any

from agentblaster import __version__
from agentblaster.config import app_home, providers_path
from agentblaster.models import EnvironmentSnapshot
from agentblaster.policy import SecurityPolicy


ENVIRONMENT_READINESS_SCHEMA_VERSION = "agentblaster.environment-readiness.v1"
REQUIRED_RUNTIME_MODULES = {
    "httpx": "HTTP provider clients",
    "pydantic": "strict config and artifact schemas",
    "yaml": "suite, policy, and matrix YAML parsing",
    "typer": "CLI command framework",
    "rich": "CLI rendering dependency",
}
OPTIONAL_RUNTIME_MODULES = {
    "keyring": "optional OS keyring / Apple Keychain secret backend",
    "playwright": "optional dashboard GUI selftest backend",
    "pytest": "optional app selftest runner",
    "build": "optional source/wheel packaging builder",
}


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


def build_environment_readiness(*, home: Path | None = None, policy: SecurityPolicy | None = None) -> dict[str, Any]:
    """Build a redaction-safe static readiness report for local setup and CI."""

    config_home = (home or app_home()).expanduser()
    provider_config = providers_path(config_home)
    active_policy = policy or SecurityPolicy()
    checks = [
        _readiness_check(
            "python-version",
            "Python runtime is new enough for AgentBlaster.",
            sys.version_info >= (3, 11),
            required=True,
            detail=f"python {sys.version.split()[0]}",
            remediation="Use Python 3.11 or newer.",
        ),
        _readiness_check(
            "platform",
            "Platform is within the supported cross-platform runtime surface.",
            platform.system() in {"Darwin", "Linux", "Windows"},
            required=True,
            detail=platform.platform(),
            remediation="Use macOS, Linux, or Windows for the Python CLI and dashboard.",
        ),
        _readiness_check(
            "runtime-dependencies",
            "Required runtime dependencies are importable.",
            all(_module_available(module) for module in REQUIRED_RUNTIME_MODULES),
            required=True,
            detail=", ".join(
                f"{module}={'yes' if _module_available(module) else 'no'}"
                for module in sorted(REQUIRED_RUNTIME_MODULES)
            ),
            remediation="Install AgentBlaster with its runtime dependencies.",
        ),
        _readiness_check(
            "config-path",
            "Provider config path can be resolved without reading secrets.",
            True,
            required=True,
            detail=str(provider_config),
            remediation="Set AGENTBLASTER_HOME or XDG_CONFIG_HOME if a different config path is required.",
        ),
        _readiness_check(
            "keyring-optional",
            "Optional keyring backend is available for OS-protected API keys.",
            _module_available("keyring"),
            required=False,
            detail="available" if _module_available("keyring") else "not installed",
            remediation="Install agentblaster[secrets] to use keyring or Apple Keychain storage.",
        ),
        _readiness_check(
            "gui-test-optional",
            "Optional GUI test backend is available.",
            _module_available("playwright"),
            required=False,
            detail="available" if _module_available("playwright") else "not installed",
            remediation="Install agentblaster[gui-test] and browser dependencies for GUI selftests.",
        ),
        _readiness_check(
            "selftest-optional",
            "Optional pytest selftest runner is available.",
            _module_available("pytest"),
            required=False,
            detail="available" if _module_available("pytest") else "not installed",
            remediation="Install agentblaster[dev] to run app selftests.",
        ),
        _readiness_check(
            "packaging-optional",
            "Optional Python build frontend is available for release packaging.",
            _module_available("build"),
            required=False,
            detail="available" if _module_available("build") else "not installed",
            remediation="Install agentblaster[dev] before building source and wheel distributions.",
        ),
    ]
    required_checks = [check for check in checks if check["required"]]
    optional_checks = [check for check in checks if not check["required"]]
    required_failed = sum(1 for check in required_checks if not check["ok"])
    optional_missing = sum(1 for check in optional_checks if not check["ok"])
    return {
        "schema_version": ENVIRONMENT_READINESS_SCHEMA_VERSION,
        "ok": required_failed == 0,
        "required_passed": len(required_checks) - required_failed,
        "required_failed": required_failed,
        "optional_available": len(optional_checks) - optional_missing,
        "optional_missing": optional_missing,
        "environment": capture_environment().model_dump(mode="json"),
        "config": {
            "home": str(config_home),
            "providers_path": str(provider_config),
            "providers_config_exists": provider_config.exists(),
        },
        "runtime_modules": {
            "required": {
                module: {
                    "available": _module_available(module),
                    "purpose": purpose,
                }
                for module, purpose in sorted(REQUIRED_RUNTIME_MODULES.items())
            },
            "optional": {
                module: {
                    "available": _module_available(module),
                    "purpose": purpose,
                }
                for module, purpose in sorted(OPTIONAL_RUNTIME_MODULES.items())
            },
        },
        "policy_controls": _policy_controls(active_policy),
        "checks": checks,
        "security_notes": [
            "Readiness is static and does not contact providers, resolve API keys, inspect keyring values, read dotenv secret files, or read provider config contents.",
            "Hostnames are represented only by SHA-256 in the environment snapshot.",
            "Policy controls are recorded as redacted booleans only; policy file contents, API keys, headers, and secret values are not embedded.",
        ],
    }


def format_environment_readiness(report: dict[str, Any]) -> str:
    lines = [
        "AgentBlaster environment readiness",
        f"ok: {str(report['ok']).lower()}",
        f"required_failed: {report['required_failed']}",
        f"optional_missing: {report['optional_missing']}",
        f"python: {report['environment'].get('python_version')}",
        f"platform: {report['environment'].get('os')} {report['environment'].get('architecture')}",
        f"providers_path: {report['config']['providers_path']}",
        "policy_controls:",
    ]
    for key, value in sorted(report.get("policy_controls", {}).items()):
        lines.append(f"- {key}: {str(value).lower()}")
    lines.append("checks:")
    for check in report["checks"]:
        status = "PASS" if check["ok"] else "MISS" if not check["required"] else "FAIL"
        required = "required" if check["required"] else "optional"
        lines.append(f"- {status} {check['id']} ({required}): {check['detail']}")
    return "\n".join(lines) + "\n"


def write_environment_readiness(output: Path, *, home: Path | None = None, policy: SecurityPolicy | None = None) -> Path:
    payload = build_environment_readiness(home=home, policy=policy)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def _policy_controls(policy: SecurityPolicy) -> dict[str, bool]:
    return {
        "allow_remote_providers": policy.allow_remote_providers,
        "allow_full_raw_traces": policy.allow_full_raw_traces,
        "require_api_key_for_remote_providers": policy.require_api_key_for_remote_providers,
        "require_cost_model_for_remote_providers": policy.require_cost_model_for_remote_providers,
        "require_rate_limits_for_remote_providers": policy.require_rate_limits_for_remote_providers,
        "require_dashboard_auth": policy.require_dashboard_auth,
        "require_cleanup_audit_log": policy.require_cleanup_audit_log,
    }


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


def _readiness_check(
    check_id: str,
    description: str,
    ok: bool,
    *,
    required: bool,
    detail: str,
    remediation: str,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "description": description,
        "ok": ok,
        "required": required,
        "detail": detail,
        "remediation": remediation,
    }


def _module_available(module: str) -> bool:
    return find_spec(module) is not None
