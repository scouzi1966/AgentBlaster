from __future__ import annotations

import html
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape


@dataclass(frozen=True)
class TestTier:
    name: str
    marker_expression: str
    command: str
    ci_default: bool
    purpose: str


@dataclass(frozen=True)
class ChromeValidationStep:
    id: str
    title: str
    action: str
    expected: str
    evidence: str


@dataclass(frozen=True)
class ChromeGuiFlow:
    id: str
    title: str
    precondition: str
    steps: tuple[str, ...]
    expected: tuple[str, ...]
    evidence: tuple[str, ...]
    selectors: tuple[str, ...] = ()
    api_surfaces: tuple[str, ...] = ()


@dataclass(frozen=True)
class SdlcGate:
    id: str
    title: str
    phase: str
    command: str
    required: bool
    blocking: bool
    evidence: str
    purpose: str


@dataclass(frozen=True)
class SelftestCommand:
    tier: TestTier
    argv: tuple[str, ...]
    env: dict[str, str]
    browser: str | None = None
    headed: bool = False
    report_dir: Path | None = None
    junit_xml: Path | None = None

    def rendered(self) -> str:
        env_prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in sorted(self.env.items()))
        command = " ".join(shlex.quote(part) for part in self.argv)
        return f"{env_prefix} {command}".strip()


SDLC_GATES: tuple[SdlcGate, ...] = (
    SdlcGate(
        id="local-fast",
        title="Fast local app-quality gate",
        phase="local",
        command="agentblaster selftest --tier fast --dry-run",
        required=True,
        blocking=True,
        evidence="Selftest plan or recorded selftest manifest for the fast tier.",
        purpose="Catch schema, contract, redaction, policy, and pure-helper regressions before longer runs.",
    ),
    SdlcGate(
        id="premerge-normal",
        title="Pre-merge deterministic CI gate",
        phase="pre-merge",
        command="agentblaster selftest --tier normal --report-dir test-reports/selftest",
        required=True,
        blocking=True,
        evidence="CI selftest manifest, optional JUnit XML, and generated selftest report.",
        purpose="Run all deterministic non-remote, non-slow, non-GUI app checks required for pull requests.",
    ),
    SdlcGate(
        id="security-required",
        title="Enterprise security invariant gate",
        phase="pre-merge",
        command="agentblaster selftest --tier security --report-dir test-reports/selftest",
        required=True,
        blocking=True,
        evidence="Security-tier selftest report plus any redaction or policy failure details.",
        purpose="Block changes that leak secrets, weaken policy enforcement, or expose unsafe dashboard behavior.",
    ),
    SdlcGate(
        id="gui-fixture",
        title="Deterministic dashboard GUI gate",
        phase="nightly",
        command="agentblaster selftest gui --browser chromium --report-dir test-reports/selftest",
        required=False,
        blocking=False,
        evidence="GUI selftest manifest, fixture path, screenshots or browser traces when failures occur.",
        purpose="Exercise dashboard setup, catalog, launch, artifact, and report flows with redacted fixtures.",
    ),
    SdlcGate(
        id="chrome-codex-review",
        title="Chrome/Codex assisted GUI evidence gate",
        phase="release",
        command="agentblaster quality gui-artifacts --output tests/gui --overwrite",
        required=False,
        blocking=False,
        evidence="Chrome dashboard plan, checklist, screenshots, and redacted API snippets when performed.",
        purpose="Capture browser-profile-dependent GUI evidence without exposing real API keys or raw traces.",
    ),
    SdlcGate(
        id="packaging-release",
        title="Packaging and installability gate",
        phase="release",
        command="agentblaster selftest --tier packaging --report-dir test-reports/selftest",
        required=True,
        blocking=True,
        evidence="Packaging-tier selftest manifest and build/install logs captured by CI.",
        purpose="Verify package metadata, console entry points, optional extras, and cross-platform path behavior before release.",
    ),
    SdlcGate(
        id="release-qualification",
        title="Release qualification bundle gate",
        phase="release",
        command="agentblaster release qualification-bundle --output-dir test-reports/release",
        required=True,
        blocking=True,
        evidence="Release qualification bundle with provenance, gate outputs, redaction scan, and skipped-check rationale.",
        purpose="Assemble corporate-consumable evidence that AgentBlaster was qualified without leaking secrets.",
    ),
    SdlcGate(
        id="redaction-scan",
        title="Shareable artifact redaction gate",
        phase="release",
        command="agentblaster security scan --path test-reports --format json --output test-reports/redaction-scan.json",
        required=True,
        blocking=True,
        evidence="Machine-readable redaction scan output for release and publication artifacts.",
        purpose="Prevent API keys, Authorization headers, raw traces, and known secret canaries from entering shared bundles.",
    ),
    SdlcGate(
        id="remote-provider-optional",
        title="Opt-in remote provider contract gate",
        phase="certification",
        command="agentblaster selftest --tier remote --report-dir test-reports/selftest",
        required=False,
        blocking=False,
        evidence="Remote selftest manifest, provider labels, credential-source notes, and cost/spend notes.",
        purpose="Certify internet-facing OpenAI/Anthropic-compatible providers only when credentials and spend approval exist.",
    ),
    SdlcGate(
        id="hardware-slow-optional",
        title="Opt-in hardware and long-run gate",
        phase="certification",
        command="agentblaster selftest --tier slow --report-dir test-reports/selftest",
        required=False,
        blocking=False,
        evidence="Slow-tier selftest manifest, hardware metadata, and skipped-check rationale.",
        purpose="Run hardware-specific or large-fixture validation without making it mandatory for every contributor.",
    ),
)


TEST_TIERS: tuple[TestTier, ...] = (
    TestTier(
        name="fast",
        marker_expression="unit or contract or security",
        command='PYTHONPATH=src pytest -q -m "unit or contract or security"',
        ci_default=True,
        purpose="Fast deterministic checks for schemas, provider contracts, redaction, policy, and pure helpers.",
    ),
    TestTier(
        name="normal",
        marker_expression="not remote and not slow and not gui",
        command='PYTHONPATH=src pytest -q -m "not remote and not slow and not gui"',
        ci_default=True,
        purpose="Default app-quality lane for local development and pull requests.",
    ),
    TestTier(
        name="security",
        marker_expression="security",
        command='PYTHONPATH=src pytest -q -m "security"',
        ci_default=True,
        purpose="Enterprise security invariants: secret handling, redaction, policy gates, and dashboard exposure.",
    ),
    TestTier(
        name="gui",
        marker_expression="gui",
        command='PYTHONPATH=src pytest -q -m "gui"',
        ci_default=False,
        purpose="Playwright browser checks for the dashboard using deterministic redacted fixtures.",
    ),
    TestTier(
        name="remote",
        marker_expression="remote",
        command='PYTHONPATH=src pytest -q -m "remote"',
        ci_default=False,
        purpose="Opt-in internet-facing provider checks that require explicit credentials and cost awareness.",
    ),
    TestTier(
        name="slow",
        marker_expression="slow",
        command='PYTHONPATH=src pytest -q -m "slow"',
        ci_default=False,
        purpose="Hardware-specific, long-running, or large-fixture checks.",
    ),
    TestTier(
        name="packaging",
        marker_expression="packaging",
        command='PYTHONPATH=src pytest -q -m "packaging"',
        ci_default=False,
        purpose="Wheel, source distribution, optional extras, and CLI entrypoint release checks.",
    ),
    TestTier(
        name="release",
        marker_expression="not remote and not slow",
        command='PYTHONPATH=src pytest -q -m "not remote and not slow"',
        ci_default=False,
        purpose="Pre-release app-quality sweep, including GUI tests when browser dependencies are installed.",
    ),
)


CHROME_DASHBOARD_VALIDATION: tuple[ChromeValidationStep, ...] = (
    ChromeValidationStep(
        id="chrome-dashboard-load",
        title="Dashboard loads on loopback",
        action="Open the local dashboard URL in Chrome through the Codex Chrome plugin.",
        expected="The AgentBlaster dashboard renders without mixed-content, extension, or console-security issues.",
        evidence="Screenshot of the hero and runs table, plus the dashboard URL and timestamp.",
    ),
    ChromeValidationStep(
        id="chrome-redaction-check",
        title="Redacted fixture data stays redacted",
        action="Inspect the dashboard table, run details API, page source, and exported report links for seeded secrets.",
        expected="No raw API keys, Authorization headers, raw trace filenames, or fixture secret strings appear.",
        evidence="Screenshot or notes showing inspected surfaces and the redaction result.",
    ),
    ChromeValidationStep(
        id="chrome-run-discovery",
        title="Run discovery is browser-visible",
        action='Use Chrome DevTools or page inspection to confirm `data-testid="runs-table"` and run rows are present.',
        expected="The table exposes stable selectors for deterministic Playwright tests and manual Chrome inspection.",
        evidence="Selector list or screenshot showing at least one `data-testid` target.",
    ),
    ChromeValidationStep(
        id="chrome-api-surfaces",
        title="Dashboard APIs are accessible and redacted",
        action="Visit `/api/providers`, `/api/suites`, `/api/runs`, and one `/api/runs/<run-id>` endpoint in Chrome.",
        expected="Responses are JSON, contain normalized metadata, and do not include raw secrets or raw provider traces.",
        evidence="Saved redacted JSON snippets or screenshots from Chrome.",
    ),
    ChromeValidationStep(
        id="chrome-responsive-layout",
        title="Dashboard handles desktop and narrow widths",
        action="Use Chrome responsive mode to inspect a desktop width and a narrow mobile width.",
        expected="The dashboard remains readable, horizontally scrolls tables when needed, and keeps status/cost/latency visible.",
        evidence="Desktop and narrow-width screenshots.",
    ),
    ChromeValidationStep(
        id="chrome-report-export",
        title="Report artifacts open cleanly",
        action="Open generated HTML report artifacts in Chrome from the dashboard or filesystem.",
        expected="Reports render with redacted fixture data and publication-quality layout without browser warnings.",
        evidence="Screenshot of the report and note of the originating run id.",
    ),
)


CHROME_GUI_TEST_FLOWS: tuple[ChromeGuiFlow, ...] = (
    ChromeGuiFlow(
        id="dashboard-smoke-redaction",
        title="Dashboard smoke and redaction review",
        precondition="Dashboard is running on loopback with deterministic redacted run fixtures and no real API keys.",
        steps=(
            "Open the dashboard URL in Chrome through the Codex Chrome plugin.",
            "Inspect the runs table, provider list, suite list, page source, and visible report links.",
            "Search visible text and JSON surfaces for seeded secret canaries.",
        ),
        expected=(
            "Dashboard loads without browser security warnings.",
            "No raw API keys, Authorization headers, raw traces, or secret canaries are visible.",
            "Stable selectors are present for deterministic browser automation.",
        ),
        evidence=(
            "Screenshot of the dashboard hero and runs table.",
            "Notes or captured snippets showing redacted provider and run data.",
        ),
        selectors=("launch-panel", "catalog-panel", "catalog-link", "runs-panel", "runs-table", "run-row"),
        api_surfaces=("/api/providers", "/api/suites", "/api/models", "/api/engine-targets", "/api/workflow-surfaces", "/api/telemetry-mappings", "/api/runs"),
    ),
    ChromeGuiFlow(
        id="provider-and-launch-flow",
        title="Provider setup and launch form flow",
        precondition="A mock local provider profile and built-in smoke suite are available; remote providers remain disabled unless policy explicitly allows them.",
        steps=(
            "Open the launch panel and inspect provider, suite, and model fields.",
            "Select the mock provider and smoke suite, enter a synthetic model id, and submit the form in a dry fixture environment.",
            "Confirm policy-denial messaging appears for disallowed remote providers or blocked capability surfaces.",
        ),
        expected=(
            "The form exposes deterministic selectors and never displays stored secrets.",
            "Successful local launches create or reference a run without contacting paid providers.",
            "Blocked launches produce clear policy or capability messages.",
        ),
        evidence=(
            "Screenshot of the launch form before submission.",
            "Screenshot or JSON snippet for the launch result or denial state.",
        ),
        selectors=("launch-form", "provider-select", "suite-select", "model-input", "launch-submit"),
        api_surfaces=("POST /api/runs", "POST /launch"),
    ),
    ChromeGuiFlow(
        id="report-artifact-review",
        title="Report artifact review",
        precondition="Fixture run contains generated redacted HTML, JSON, Markdown, publication, or card artifacts allowlisted for dashboard serving.",
        steps=(
            "Open each report artifact link from the run table or run detail surface.",
            "Confirm the browser renders HTML/card artifacts and downloads or displays JSON/Markdown artifacts without warnings.",
            "Inspect report content for redaction and corporate/publication readiness.",
        ),
        expected=(
            "Only allowlisted report artifacts are served.",
            "Reports render without mixed-content or unsafe-file warnings.",
            "Reports contain normalized metrics, provenance, and no raw secrets.",
        ),
        evidence=(
            "Screenshot of a rendered HTML or card report.",
            "List of artifact URLs opened and any blocked artifacts.",
        ),
        selectors=("report-artifact-link",),
        api_surfaces=("GET /runs/<run-id>/artifacts/<artifact>",),
    ),
    ChromeGuiFlow(
        id="responsive-api-review",
        title="Responsive layout and redacted API review",
        precondition="Dashboard fixture data includes at least one completed run with summary metrics and one empty or failed state fixture.",
        steps=(
            "Use Chrome responsive mode for desktop and narrow mobile widths.",
            "Open redacted JSON endpoints directly in Chrome.",
            "Inspect empty, failed, and completed run states when fixtures are available.",
        ),
        expected=(
            "Tables remain readable or horizontally scrollable at narrow widths.",
            "Status, cost, latency, and pass-rate signals remain visible.",
            "JSON endpoints are redacted and stable enough for browser automation snapshots.",
        ),
        evidence=(
            "Desktop and narrow-width screenshots.",
            "Redacted JSON snippets for providers, suites, runs, and run detail.",
        ),
        selectors=("catalog-panel", "empty-state", "runs-table", "run-row"),
        api_surfaces=("/api/catalogs", "/api/providers", "/api/suites", "/api/models", "/api/engine-targets", "/api/workflow-surfaces", "/api/telemetry-mappings", "/api/runs", "/api/runs/<run-id>"),
    ),
)


def list_sdlc_gates() -> list[SdlcGate]:
    return list(SDLC_GATES)


def build_sdlc_gate_catalog() -> dict[str, object]:
    return {
        "schema_version": "agentblaster.sdlc-gates.v1",
        "scope": "AgentBlaster application self-test and release-quality gates",
        "boundary": "These gates validate AgentBlaster itself, not benchmarked inference engines or model quality.",
        "phases": sorted({gate.phase for gate in SDLC_GATES}),
        "gates": [
            {
                "id": gate.id,
                "title": gate.title,
                "phase": gate.phase,
                "command": gate.command,
                "required": gate.required,
                "blocking": gate.blocking,
                "evidence": gate.evidence,
                "purpose": gate.purpose,
            }
            for gate in SDLC_GATES
        ],
    }


def render_sdlc_gate_catalog_json() -> str:
    return json.dumps(build_sdlc_gate_catalog(), indent=2, sort_keys=True) + "\n"


def render_sdlc_gate_catalog_markdown() -> str:
    catalog = build_sdlc_gate_catalog()
    lines = [
        "# AgentBlaster SDLC Gate Catalog",
        "",
        f"Schema: `{catalog['schema_version']}`",
        "",
        str(catalog["boundary"]),
        "",
        "| Gate | Phase | Required | Blocking | Command | Evidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for gate in catalog["gates"]:
        assert isinstance(gate, dict)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{gate['id']}`",
                    str(gate["phase"]),
                    str(gate["required"]).lower(),
                    str(gate["blocking"]).lower(),
                    f"`{gate['command']}`",
                    str(gate["evidence"]),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Purpose", ""])
    for gate in catalog["gates"]:
        assert isinstance(gate, dict)
        lines.append(f"- `{gate['id']}`: {gate['purpose']}")
    return "\n".join(lines) + "\n"


def list_test_tiers() -> list[TestTier]:
    return list(TEST_TIERS)


def get_test_tier(name: str) -> TestTier:
    for tier in TEST_TIERS:
        if tier.name == name:
            return tier
    available = ", ".join(tier.name for tier in TEST_TIERS)
    raise ValueError(f"unknown test tier {name!r}; available tiers: {available}")


def list_chrome_validation_steps() -> list[ChromeValidationStep]:
    return list(CHROME_DASHBOARD_VALIDATION)


def list_chrome_gui_test_flows() -> list[ChromeGuiFlow]:
    return list(CHROME_GUI_TEST_FLOWS)


def build_chrome_gui_test_plan(
    *,
    dashboard_url: str = "http://127.0.0.1:8765",
    fixture_profile: str = "deterministic-redacted",
) -> dict[str, object]:
    return {
        "schema_version": "agentblaster.chrome-gui-plan.v1",
        "purpose": "Chrome/Codex-assisted dashboard GUI validation plan for AgentBlaster selftesting.",
        "dashboard_url": dashboard_url,
        "fixture_profile": fixture_profile,
        "determinism": "Static plan template; use mock providers and seeded redacted artifacts for execution.",
        "tooling": ["Codex Chrome plugin", "Chrome DevTools", "Playwright parity target"],
        "safety": [
            "Do not enter or expose real API keys.",
            "Do not enable unrestricted host tools during GUI validation.",
            "Use redacted fixture runs and mock providers by default.",
            "Convert recurring Chrome findings into deterministic pytest or Playwright checks.",
        ],
        "flows": [
            {
                "id": flow.id,
                "title": flow.title,
                "precondition": flow.precondition,
                "steps": list(flow.steps),
                "expected": list(flow.expected),
                "evidence": list(flow.evidence),
                "selectors": [f'data-testid="{selector}"' for selector in flow.selectors],
                "api_surfaces": list(flow.api_surfaces),
            }
            for flow in CHROME_GUI_TEST_FLOWS
        ],
    }


def render_chrome_gui_plan_json(
    *,
    dashboard_url: str = "http://127.0.0.1:8765",
    fixture_profile: str = "deterministic-redacted",
) -> str:
    plan = build_chrome_gui_test_plan(dashboard_url=dashboard_url, fixture_profile=fixture_profile)
    return json.dumps(plan, indent=2, sort_keys=True) + "\n"


def render_chrome_gui_plan_markdown(
    *,
    dashboard_url: str = "http://127.0.0.1:8765",
    fixture_profile: str = "deterministic-redacted",
) -> str:
    plan = build_chrome_gui_test_plan(dashboard_url=dashboard_url, fixture_profile=fixture_profile)
    lines = [
        "# AgentBlaster Chrome GUI Self-Test Plan",
        "",
        f"Dashboard URL: `{plan['dashboard_url']}`",
        f"Fixture profile: `{plan['fixture_profile']}`",
        "",
        "## Safety",
        "",
    ]
    lines.extend(f"- {item}" for item in plan["safety"])
    lines.extend(["", "## Flows", ""])
    for flow in plan["flows"]:
        assert isinstance(flow, dict)
        lines.extend([
            f"### {flow['id']}: {flow['title']}",
            "",
            f"Precondition: {flow['precondition']}",
            "",
            "Steps:",
        ])
        lines.extend(f"- {item}" for item in flow["steps"])
        lines.append("")
        lines.append("Expected:")
        lines.extend(f"- {item}" for item in flow["expected"])
        lines.append("")
        lines.append("Evidence:")
        lines.extend(f"- {item}" for item in flow["evidence"])
        if flow["selectors"]:
            lines.append("")
            lines.append("Selectors:")
            lines.extend(f"- `{item}`" for item in flow["selectors"])
        if flow["api_surfaces"]:
            lines.append("")
            lines.append("API surfaces:")
            lines.extend(f"- `{item}`" for item in flow["api_surfaces"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_chrome_validation_markdown() -> str:
    lines = [
        "# AgentBlaster Chrome GUI Validation Checklist",
        "",
        "Use this checklist with the Codex Chrome plugin for interactive dashboard validation.",
        "Every finding should be converted into a deterministic Playwright or pytest fixture before it becomes a release gate.",
        "",
    ]
    for step in CHROME_DASHBOARD_VALIDATION:
        lines.extend(
            [
                f"## {step.id}: {step.title}",
                "",
                f"- Action: {step.action}",
                f"- Expected: {step.expected}",
                f"- Evidence: {step.evidence}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def build_selftest_command(
    tier_name: str,
    *,
    browser: str | None = None,
    headed: bool = False,
    report_dir: Path | None = None,
    junit_xml: Path | None = None,
    extra_args: tuple[str, ...] = (),
) -> SelftestCommand:
    tier = get_test_tier(tier_name)
    env = {"PYTHONPATH": "src"}
    argv = ["pytest", "-q", "-m", tier.marker_expression]
    if tier.name == "gui":
        if browser is not None:
            env["AGENTBLASTER_GUI_BROWSER"] = browser
        if headed:
            env["AGENTBLASTER_GUI_HEADED"] = "1"
    if junit_xml is not None:
        argv.extend(["--junitxml", str(junit_xml)])
    argv.extend(extra_args)
    return SelftestCommand(
        tier=tier,
        argv=tuple(argv),
        env=env,
        browser=browser,
        headed=headed,
        report_dir=report_dir,
        junit_xml=junit_xml,
    )


def render_selftest_plan(command: SelftestCommand) -> str:
    lines = [
        f"tier: {command.tier.name}",
        f"purpose: {command.tier.purpose}",
        f"ci_default: {str(command.tier.ci_default).lower()}",
        f"marker: {command.tier.marker_expression}",
        f"command: {command.rendered()}",
    ]
    if command.browser is not None:
        lines.append(f"browser: {command.browser}")
    if command.headed:
        lines.append("headed: true")
    if command.junit_xml is not None:
        lines.append(f"junit_xml: {command.junit_xml}")
    if command.report_dir is not None:
        lines.append(f"report_dir: {command.report_dir}")
    return "\n".join(lines) + "\n"


def run_selftest_command(command: SelftestCommand) -> int:
    env = os.environ.copy()
    env.update(command.env)
    started_at = datetime.now(UTC)
    exit_code = 1
    try:
        result = subprocess.run(command.argv, env=env, check=False)  # noqa: S603 - argv is constructed, not shell input
        exit_code = result.returncode
        return exit_code
    finally:
        completed_at = datetime.now(UTC)
        if command.report_dir is not None:
            write_selftest_execution_manifest(
                command=command,
                started_at=started_at,
                completed_at=completed_at,
                exit_code=exit_code,
            )


def write_selftest_execution_manifest(
    *,
    command: SelftestCommand,
    started_at: datetime,
    completed_at: datetime,
    exit_code: int,
) -> Path:
    if command.report_dir is None:
        raise ValueError("report_dir is required")
    run_id = f"selftest_{started_at.strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = command.report_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    duration_ms = round(max((completed_at - started_at).total_seconds() * 1000, 0.0), 3)
    payload = {
        "run_id": run_id,
        "tier": command.tier.name,
        "purpose": command.tier.purpose,
        "marker_expression": command.tier.marker_expression,
        "command": command.rendered(),
        "argv": list(command.argv),
        "env": command.env,
        "browser": command.browser,
        "headed": command.headed,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "ok": exit_code == 0,
        "junit_xml": str(command.junit_xml) if command.junit_xml else None,
    }
    path = run_dir / "selftest.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def generate_selftest_reports(run: str | Path, formats: list[str], *, base_dir: Path = Path("test-reports/selftest")) -> list[Path]:
    run_dir = resolve_selftest_run(run, base_dir=base_dir)
    manifest_path = run_dir / "selftest.json"
    if not manifest_path.exists():
        raise ValueError(f"missing selftest manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    generated: list[Path] = []
    for report_format in formats:
        normalized = report_format.strip().lower()
        if not normalized:
            continue
        if normalized == "json":
            path = run_dir / "selftest-report.json"
            path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            generated.append(path)
        elif normalized == "html":
            path = run_dir / "selftest-report.html"
            path.write_text(_selftest_html_report(manifest), encoding="utf-8")
            generated.append(path)
        elif normalized == "junit":
            path = run_dir / "selftest-report.junit.xml"
            path.write_text(_selftest_junit_report(manifest), encoding="utf-8")
            generated.append(path)
        else:
            raise ValueError(f"unsupported selftest report format: {report_format}")
    return generated


def resolve_selftest_run(run: str | Path, *, base_dir: Path = Path("test-reports/selftest")) -> Path:
    candidate = Path(run)
    if candidate.exists():
        return candidate
    return base_dir / str(run)


def _selftest_html_report(manifest: dict) -> str:
    status = "PASS" if manifest.get("ok") else "FAIL"
    status_color = "#0b6b3a" if manifest.get("ok") else "#a52222"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>AgentBlaster Selftest {html.escape(str(manifest.get("run_id", "")))}</title>
  <style>
    body {{ font-family: Avenir Next, Trebuchet MS, sans-serif; margin: 40px; color: #172026; }}
    code {{ background: #f1f4f7; padding: 2px 5px; border-radius: 4px; }}
    .status {{ font-weight: 800; color: {status_color}; }}
  </style>
</head>
<body>
  <h1>AgentBlaster Selftest Report</h1>
  <p>Status: <span class="status">{status}</span></p>
  <p>Run: <code>{html.escape(str(manifest.get("run_id", "")))}</code></p>
  <p>Tier: <code>{html.escape(str(manifest.get("tier", "")))}</code></p>
  <p>Marker: <code>{html.escape(str(manifest.get("marker_expression", "")))}</code></p>
  <p>Command: <code>{html.escape(str(manifest.get("command", "")))}</code></p>
  <p>Started: {html.escape(str(manifest.get("started_at", "")))}</p>
  <p>Completed: {html.escape(str(manifest.get("completed_at", "")))}</p>
  <p>Duration ms: {html.escape(str(manifest.get("duration_ms", "")))}</p>
  <p>Exit code: {html.escape(str(manifest.get("exit_code", "")))}</p>
</body>
</html>
"""


def _selftest_junit_report(manifest: dict) -> str:
    run_id = xml_escape(str(manifest.get("run_id", "selftest")))
    tier = xml_escape(str(manifest.get("tier", "unknown")))
    duration_seconds = str((float(manifest.get("duration_ms") or 0.0)) / 1000)
    failures = "0"
    failure = ""
    if not manifest.get("ok"):
        failures = "1"
        failure = (
            f'<failure message="selftest command failed with exit code {xml_escape(str(manifest.get("exit_code", "")))}">'
            f'{xml_escape(str(manifest.get("command", "")))}</failure>'
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<testsuite name="agentblaster-selftest-{tier}" tests="1" failures="{failures}" time="{duration_seconds}">\n'
        f'  <testcase classname="agentblaster.selftest" name="{run_id}" time="{duration_seconds}">{failure}</testcase>\n'
        "</testsuite>\n"
    )


GUI_TEST_SPEC_SCHEMA = "agentblaster.gui-test-spec.v1"
_GUI_SECURITY_CANARIES = ("sk-", "Authorization", "Bearer", "x-api-key", "AGENTBLASTER_SECRET_CANARY")


def render_gui_test_spec_json(
    *,
    dashboard_url: str = "http://127.0.0.1:8765",
    fixture_dir: str = "tests/fixtures/dashboard-runs",
    evidence_dir: str = "test-reports/gui",
    browser: str = "chrome",
) -> str:
    chrome_plan = json.loads(render_chrome_gui_plan_json(dashboard_url=dashboard_url, fixture_profile=fixture_dir))
    spec = {
        "schema_version": GUI_TEST_SPEC_SCHEMA,
        "scope": "AgentBlaster app self-test dashboard GUI",
        "boundary": "These checks validate AgentBlaster, not benchmarked inference engines.",
        "dashboard": {
            "url": dashboard_url,
            "start_command": f"agentblaster dashboard --runs {fixture_dir} --host 127.0.0.1 --port 8765",
            "bind_policy": "Loopback by default; non-loopback requires explicit policy and authentication.",
        },
        "fixtures": {
            "directory": fixture_dir,
            "generate_command": f"agentblaster quality dashboard-fixture --output {fixture_dir} --overwrite",
            "requirements": [
                "Use deterministic fixture runs or redacted local benchmark artifacts.",
                "Do not use real API keys, raw provider traces, browser history, or production customer data.",
            ],
        },
        "ci": {
            "runner": "pytest + optional Playwright",
            "pytest_command": f"PYTHONPATH=src AGENTBLASTER_GUI_BROWSER={browser} pytest -q tests/gui -m gui",
            "selftest_command": f"agentblaster selftest gui --browser {browser}",
            "optional_extra": "agentblaster[gui-test]",
            "skip_behavior": "GUI tests skip cleanly when Playwright or the requested browser is unavailable.",
        },
        "chrome_codex": {
            "tool": "Codex Chrome plugin",
            "use_cases": [
                "Interactive dashboard inspection with the user's Chrome profile when needed.",
                "Responsive screenshots for release evidence.",
                "Manual or semi-automated review of browser-visible redaction and security headers.",
            ],
            "evidence_directory": evidence_dir,
            "plan": chrome_plan,
        },
        "release_evidence": [
            "gui-test-spec.json",
            "chrome-dashboard-plan.json",
            "chrome-dashboard-checklist.md",
            "Desktop and narrow-width screenshots when Chrome/Codex validation is performed.",
            "Redacted API snippets for providers, suites, runs, and one run detail.",
        ],
        "security_canaries": list(_GUI_SECURITY_CANARIES),
    }
    return json.dumps(spec, indent=2, sort_keys=True) + "\n"


def render_gui_test_spec_markdown(
    *,
    dashboard_url: str = "http://127.0.0.1:8765",
    fixture_dir: str = "tests/fixtures/dashboard-runs",
    evidence_dir: str = "test-reports/gui",
    browser: str = "chrome",
) -> str:
    spec = json.loads(
        render_gui_test_spec_json(
            dashboard_url=dashboard_url,
            fixture_dir=fixture_dir,
            evidence_dir=evidence_dir,
            browser=browser,
        )
    )
    lines = [
        "# AgentBlaster GUI Self-Test Specification",
        "",
        f"Schema: `{spec['schema_version']}`",
        "",
        "This specification validates AgentBlaster's dashboard and GUI-facing app behavior. It must not be mixed into benchmark scores for inference engines.",
        "",
        "## Deterministic Fixture Lane",
        "",
        f"- Generate fixtures: `{spec['fixtures']['generate_command']}`",
        f"- Start dashboard: `{spec['dashboard']['start_command']}`",
        f"- Dashboard URL: `{spec['dashboard']['url']}`",
        "",
        "## CI GUI Lane",
        "",
        f"- Pytest command: `{spec['ci']['pytest_command']}`",
        f"- Selftest command: `{spec['ci']['selftest_command']}`",
        f"- Optional extra: `{spec['ci']['optional_extra']}`",
        f"- Skip behavior: {spec['ci']['skip_behavior']}",
        "",
        "## Chrome/Codex Evidence Lane",
        "",
        f"- Tool: {spec['chrome_codex']['tool']}",
        f"- Evidence directory: `{spec['chrome_codex']['evidence_directory']}`",
        "- Required Chrome/Codex flows:",
    ]
    for flow in spec["chrome_codex"]["plan"]["flows"]:
        lines.append(f"  - `{flow['id']}`: {flow['title']}")
    lines.extend(
        [
            "",
            "## Security Canaries",
            "",
            *[f"- `{canary}`" for canary in spec["security_canaries"]],
            "",
            "## Release Evidence",
            "",
            *[f"- {item}" for item in spec["release_evidence"]],
            "",
        ]
    )
    return "\n".join(lines)


def write_gui_test_artifacts(
    output_dir: Path,
    *,
    dashboard_url: str = "http://127.0.0.1:8765",
    fixture_dir: str = "tests/fixtures/dashboard-runs",
    evidence_dir: str = "test-reports/gui",
    browser: str = "chrome",
    overwrite: bool = False,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "gui-test-spec.json": render_gui_test_spec_json(
            dashboard_url=dashboard_url,
            fixture_dir=fixture_dir,
            evidence_dir=evidence_dir,
            browser=browser,
        ),
        "gui-test-spec.md": render_gui_test_spec_markdown(
            dashboard_url=dashboard_url,
            fixture_dir=fixture_dir,
            evidence_dir=evidence_dir,
            browser=browser,
        ),
        "chrome-dashboard-plan.json": render_chrome_gui_plan_json(
            dashboard_url=dashboard_url,
            fixture_profile=fixture_dir,
        ),
        "chrome-dashboard-checklist.md": render_chrome_validation_markdown(),
    }
    written: list[Path] = []
    for name, content in artifacts.items():
        path = output_dir / name
        if path.exists() and not overwrite:
            raise FileExistsError(f"refusing to overwrite existing GUI test artifact: {path}")
        path.write_text(content)
        written.append(path)
    return written
