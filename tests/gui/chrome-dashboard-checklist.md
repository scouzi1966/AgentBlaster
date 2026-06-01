# AgentBlaster Chrome GUI Validation Checklist

Use this checklist with the Codex Chrome plugin for profile-aware dashboard validation. It complements deterministic Playwright tests and should not replace CI automation.

## Preconditions

- Start the dashboard on loopback: `agentblaster dashboard --runs runs --host 127.0.0.1 --port 8765`.
- Use deterministic fixture runs or redacted local benchmark artifacts.
- Do not use live API keys, raw provider traces, or production customer data for screenshots.

## Checks

- Dashboard load: open `http://127.0.0.1:8765` in Chrome and capture the hero plus runs table.
- Launch form: confirm the provider, suite, model, raw-trace, concurrency, and allow-remote controls are visible without JavaScript.
- Redaction: inspect the page, `/api/providers`, `/api/runs`, and one `/api/runs/<run-id>` response for seeded secrets or raw authorization headers.
- Stable selectors: confirm `data-testid="launch-form"`, `data-testid="runs-panel"`, `data-testid="runs-table"`, and `data-testid="run-row"` are present.
- Report links: confirm generated `report.html`, `report.pdf`, `publication.json`, and `report-card.svg` links open only through allowlisted artifact URLs.
- Provider-contract evidence: inspect the Review evidence panel and `/api/review-artifacts` for provider-contract direct/proxy/not-covered capability evidence without raw provider payloads.
- Responsive layout: inspect desktop and narrow mobile widths with Chrome responsive mode.
- Security headers: inspect the network response for `x-content-type-options`, `referrer-policy`, and `content-security-policy`.
- Reports: open generated HTML reports in Chrome and confirm no raw secrets or raw trace filenames are rendered.

## Evidence To Attach

- Dashboard URL, run id, timestamp, and platform.
- Desktop screenshot.
- Narrow-width screenshot.
- Redacted API response snippets or screenshots.
- Screenshot or redacted `/api/review-artifacts` snippet showing provider-contract capability evidence.
- Notes for any behavior that should become a deterministic Playwright or pytest regression.
