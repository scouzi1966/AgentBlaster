from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from agentblaster.errors import ConfigError
from agentblaster.models import (
    RunIntegrityManifest,
    RunIntegrityVerification,
    RunSignatureManifest,
    RunSignatureVerification,
)


INTEGRITY_FILENAME = "integrity.json"
SIGNATURE_FILENAME = "signature.json"


def load_integrity_manifest(run_dir: Path) -> RunIntegrityManifest:
    path = run_dir / INTEGRITY_FILENAME
    if not path.exists():
        raise ConfigError(f"missing integrity manifest: {path}")
    try:
        return RunIntegrityManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise ConfigError(f"invalid integrity manifest at {path}: {exc}") from exc


def verify_run_integrity(run_dir: Path, *, allow_extra: bool = True) -> RunIntegrityVerification:
    manifest = load_integrity_manifest(run_dir)
    missing: list[str] = []
    changed: list[str] = []

    for relative_path, expected_digest in sorted(manifest.artifacts.items()):
        _reject_unsafe_artifact_path(relative_path)
        path = run_dir / relative_path
        if not path.exists():
            missing.append(relative_path)
            continue
        actual_digest = sha256_file(path)
        if actual_digest != expected_digest:
            changed.append(relative_path)

    expected_paths = set(manifest.artifacts)
    extra = []
    if not allow_extra:
        extra = [
            path.relative_to(run_dir).as_posix()
            for path in sorted(item for item in run_dir.rglob("*") if item.is_file())
            if path.relative_to(run_dir).as_posix() not in expected_paths
            and path.relative_to(run_dir).as_posix() != INTEGRITY_FILENAME
            and path.relative_to(run_dir).as_posix() != SIGNATURE_FILENAME
        ]

    return RunIntegrityVerification(
        run_id=manifest.run_id,
        ok=not missing and not changed and not extra,
        checked=len(manifest.artifacts) - len(missing),
        missing=missing,
        changed=changed,
        extra=extra,
    )


def sign_run_integrity(run_dir: Path, *, key: str, key_id: str) -> Path:
    if not key:
        raise ConfigError("signing key must not be empty")
    integrity = load_integrity_manifest(run_dir)
    payload = _signature_payload(integrity)
    signature = _hmac_sha256(key, payload)
    manifest = RunSignatureManifest(
        run_id=integrity.run_id,
        created_at=datetime.now(UTC).isoformat(),
        key_id=key_id,
        signature=signature,
        signed_artifacts=dict(sorted(integrity.artifacts.items())),
    )
    path = run_dir / SIGNATURE_FILENAME
    path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def load_signature_manifest(run_dir: Path) -> RunSignatureManifest:
    path = run_dir / SIGNATURE_FILENAME
    if not path.exists():
        raise ConfigError(f"missing signature manifest: {path}")
    try:
        return RunSignatureManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise ConfigError(f"invalid signature manifest at {path}: {exc}") from exc


def verify_run_signature(
    run_dir: Path,
    *,
    key: str,
    allow_extra: bool = True,
) -> RunSignatureVerification:
    if not key:
        raise ConfigError("signing key must not be empty")
    integrity = load_integrity_manifest(run_dir)
    signature = load_signature_manifest(run_dir)
    if signature.run_id != integrity.run_id:
        integrity_verification = verify_run_integrity(run_dir, allow_extra=allow_extra)
        return RunSignatureVerification(
            run_id=integrity.run_id,
            ok=False,
            signature_ok=False,
            integrity_ok=integrity_verification.ok,
            key_id=signature.key_id,
            checked=integrity_verification.checked,
            missing=integrity_verification.missing,
            changed=integrity_verification.changed,
            extra=integrity_verification.extra,
        )
    expected_signature = _hmac_sha256(key, _signature_payload(integrity))
    signature_ok = hmac.compare_digest(signature.signature, expected_signature)
    integrity_verification = verify_run_integrity(run_dir, allow_extra=allow_extra)
    return RunSignatureVerification(
        run_id=integrity.run_id,
        ok=signature_ok and integrity_verification.ok,
        signature_ok=signature_ok,
        integrity_ok=integrity_verification.ok,
        key_id=signature.key_id,
        checked=integrity_verification.checked,
        missing=integrity_verification.missing,
        changed=integrity_verification.changed,
        extra=integrity_verification.extra,
    )


def _reject_unsafe_artifact_path(relative_path: str) -> None:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ConfigError(f"unsafe artifact path in integrity manifest: {relative_path}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _signature_payload(integrity: RunIntegrityManifest) -> bytes:
    payload = {
        "algorithm": integrity.algorithm,
        "artifacts": dict(sorted(integrity.artifacts.items())),
        "run_id": integrity.run_id,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hmac_sha256(key: str, payload: bytes) -> str:
    return hmac.new(key.encode("utf-8"), payload, hashlib.sha256).hexdigest()
