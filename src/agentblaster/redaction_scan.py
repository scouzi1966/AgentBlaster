from __future__ import annotations

import json
import re
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from pydantic import BaseModel, ConfigDict, Field

from agentblaster.errors import ConfigError


SCAN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai_api_key", re.compile(r"sk-[A-Za-z0-9_\-]{16,}")),
    ("anthropic_api_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}")),
    ("github_token", re.compile(r"gh[opusr]_[A-Za-z0-9_]{16,}")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9._\-]{16,}", re.IGNORECASE)),
    ("aws_access_key_id", re.compile(r"AKIA[0-9A-Z]{16}")),
]
TEXT_SUFFIXES = {
    ".csv",
    ".html",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".svg",
    ".txt",
    ".yaml",
    ".yml",
    ".xml",
}
ZIP_SUFFIXES = {".zip"}


class RedactionScanFinding(BaseModel):
    """Secret-like pattern finding without the matched secret value."""

    model_config = ConfigDict(extra="forbid")

    path: str
    entry: str | None = None
    line: int | None = None
    pattern: str
    message: str


class RedactionScanReport(BaseModel):
    """Redaction scan report for release/publishing gates."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    total_paths: int = Field(ge=0)
    scanned_items: int = Field(ge=0)
    skipped_items: int = Field(ge=0)
    findings: list[RedactionScanFinding] = Field(default_factory=list)
    security_notes: list[str] = Field(default_factory=list)


def scan_paths(paths: list[Path], *, max_bytes: int = 2_000_000) -> RedactionScanReport:
    if not paths:
        raise ConfigError("redaction scan requires at least one path")
    findings: list[RedactionScanFinding] = []
    scanned = 0
    skipped = 0
    for input_path in paths:
        if not input_path.exists():
            raise ConfigError(f"redaction scan path does not exist: {input_path}")
        for path in _iter_files(input_path):
            if path.suffix.lower() in ZIP_SUFFIXES:
                zip_scanned, zip_skipped = _scan_zip(path, findings, max_bytes=max_bytes)
                scanned += zip_scanned
                skipped += zip_skipped
                continue
            if not _looks_textual(path):
                skipped += 1
                continue
            try:
                data = path.read_bytes()
            except OSError as exc:
                raise ConfigError(f"unable to read scan path {path}: {exc}") from exc
            if len(data) > max_bytes:
                skipped += 1
                continue
            text = _decode_text(data)
            if text is None:
                skipped += 1
                continue
            scanned += 1
            findings.extend(_scan_text(text, path=str(path), entry=None))
    return RedactionScanReport(
        ok=not findings,
        total_paths=len(paths),
        scanned_items=scanned,
        skipped_items=skipped,
        findings=findings,
        security_notes=[
            "Redaction scan reports pattern names and locations only; matched secret values are never included.",
            "This is a deterministic regex gate for common secret formats, not a complete DLP system.",
        ],
    )


def format_redaction_scan_report(report: RedactionScanReport) -> str:
    lines = [
        f"ok: {str(report.ok).lower()}",
        f"total_paths: {report.total_paths}",
        f"scanned_items: {report.scanned_items}",
        f"skipped_items: {report.skipped_items}",
        f"findings: {len(report.findings)}",
    ]
    for finding in report.findings:
        location = finding.path if finding.entry is None else f"{finding.path}!{finding.entry}"
        if finding.line is not None:
            location = f"{location}:{finding.line}"
        lines.append(f"{finding.pattern}	{location}	{finding.message}")
    return "
".join(lines) + "
"


def redaction_scan_json(report: RedactionScanReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "
"


def _iter_files(path: Path):
    if path.is_file():
        yield path
        return
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        yield child


def _looks_textual(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.suffix == ""


def _scan_zip(path: Path, findings: list[RedactionScanFinding], *, max_bytes: int) -> tuple[int, int]:
    scanned = 0
    skipped = 0
    try:
        with ZipFile(path) as archive:
            for info in sorted(archive.infolist(), key=lambda item: item.filename):
                if info.is_dir():
                    continue
                entry_path = Path(info.filename)
                if entry_path.suffix.lower() not in TEXT_SUFFIXES:
                    skipped += 1
                    continue
                if info.file_size > max_bytes:
                    skipped += 1
                    continue
                text = _decode_text(archive.read(info))
                if text is None:
                    skipped += 1
                    continue
                scanned += 1
                findings.extend(_scan_text(text, path=str(path), entry=info.filename))
    except (OSError, BadZipFile) as exc:
        raise ConfigError(f"unable to scan zip artifact {path}: {exc}") from exc
    return scanned, skipped


def _decode_text(data: bytes) -> str | None:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _scan_text(text: str, *, path: str, entry: str | None) -> list[RedactionScanFinding]:
    findings: list[RedactionScanFinding] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for name, pattern in SCAN_PATTERNS:
            if pattern.search(line):
                findings.append(
                    RedactionScanFinding(
                        path=path,
                        entry=entry,
                        line=line_number,
                        pattern=name,
                        message="secret-like pattern detected; matched value suppressed",
                    )
                )
    return findings
