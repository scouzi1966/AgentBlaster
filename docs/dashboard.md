# AgentBlaster Dashboard

The dashboard is an optional browser surface over the same provider registry, suite registry, and run artifacts used by the CLI.

Start it on loopback:

```bash
agentblaster dashboard --runs runs --host 127.0.0.1 --port 8765
```

Enable token authentication:

```bash
export AGENTBLASTER_DASHBOARD_TOKEN="$(openssl rand -hex 32)"
agentblaster dashboard \
  --runs runs \
  --host 127.0.0.1 \
  --port 8765 \
  --policy agentblaster.policy.yaml \
  --auth-token-env AGENTBLASTER_DASHBOARD_TOKEN
```

Bind beyond loopback only with explicit opt-in and token authentication:

```bash
agentblaster dashboard \
  --runs runs \
  --host 0.0.0.0 \
  --port 8765 \
  --policy agentblaster.policy.yaml \
  --allow-non-loopback \
  --auth-token-env AGENTBLASTER_DASHBOARD_TOKEN
```

## Capabilities

- Browse completed run summaries.
- View suite hash and provenance metadata for reproducibility checks.
- Open safe metrics summary artifacts when Prometheus snapshots are configured.
- Inspect redacted provider and suite metadata through API endpoints.
- Launch built-in suites against configured providers from a no-JavaScript HTML form.
- Generate report artifacts for completed runs from the browser or API.
- Keep remote providers blocked by default unless the operator explicitly checks `allow remote provider`.
- Open generated report artifacts through allowlisted links.
- Show a visible security posture panel for dashboard auth, configured remote providers, insecure TLS providers, full raw trace runs, and allowlisted artifact serving.

## Browser Routes

- `/`: dashboard HTML.
- `/login`: no-JavaScript token login form when dashboard auth is enabled.
- `/logout`: clears the dashboard auth cookie.
- `/launch`: server-side form endpoint for launching a run.
- `/runs/<run-id>/reports`: server-side form endpoint for generating reports.
- `/api/providers`: redacted provider registry.
- `/api/suites`: built-in suite metadata.
- `/api/runs`: completed run summaries.
- `/api/runs/<run-id>`: manifest, summary, and normalized results.
- `/api/runs/<run-id>/reports`: JSON endpoint for generating report artifacts.
- `/runs/<run-id>/artifacts/<artifact>`: allowlisted report artifact serving.

Allowed artifact names:

- `report.html`
- `report.md`
- `summary.json`
- `publication.json`
- `report-card.svg`
- `metrics/prometheus-summary.json`

## Security Posture

- The dashboard binds to loopback by default.
- Non-loopback binding requires explicit CLI opt-in and token authentication.
- Policy files can restrict dashboard hosts and ports, require dashboard auth even on loopback, and disable or explicitly allow non-loopback binding.
- Non-loopback startup must satisfy both the policy file and CLI safety checks: `allow_dashboard_non_loopback: true`, `--allow-non-loopback`, and `--auth-token-env`.
- Token authentication can use a browser login cookie or `Authorization: Bearer <token>` for API clients.
- Dashboard tokens are read from an environment variable and are never written to provider config, run artifacts, reports, or cookies.
- Dashboard tokens must be at least 16 characters; use a high-entropy value from an enterprise secret manager or OS-protected shell environment.
- The auth cookie stores a SHA-256 token digest, not the raw token, and is marked `HttpOnly` and `SameSite=Strict`.
- CSP disables scripts and restricts form submission to same-origin.
- Artifact serving is allowlisted and does not expose raw traces or manifests.
- Report generation reads existing run artifacts and writes only allowlisted report formats.
- Raw Prometheus before/after text is not served by the dashboard; only the derived metrics summary JSON is allowlisted.
- Secrets are resolved through provider references; the browser form never accepts raw API keys.
- The security posture panel is derived from redacted provider metadata and run manifests. It flags configured providers that disable TLS verification and does not read raw provider payloads or raw trace files.

Dashboard policy fields:

```yaml
allowed_dashboard_hosts:
  - 127.0.0.1
  - localhost
allowed_dashboard_ports:
  - 8765
allow_dashboard_non_loopback: false
require_dashboard_auth: true
```
