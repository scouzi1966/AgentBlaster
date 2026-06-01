# Evidence Bundles

Evidence bundles package static, redaction-safe review artifacts for corporate approval, media support, or release governance. They do not run benchmarks, contact providers, resolve secrets, execute tools, or read raw run artifacts.

## Create A Bundle

```bash
agentblaster evidence bundle \
  --suite-file examples/suites/toolsim.yaml \
  --policy agentblaster.policy.yaml \
  --include-provider-audit \
  --output-dir evidence \
  --audit-log audit/control-plane.jsonl
```

For a built-in suite:

```bash
agentblaster evidence bundle --suite trace-replay --output-dir evidence
```

## Contents

Each `.agentblaster-evidence.zip` contains fixed artifact names:

- `manifest.json`: bundle metadata, artifact SHA-256 checksums, and redaction/security notes.
- `suite-audit.json`: static suite provenance, risk, and capability-surface audit.
- `catalogs/simulated-tools.json`: deterministic simulated tool inventory.
- `catalogs/mcp-profiles.json`: deterministic MCP fixture profile inventory.
- `catalogs/skills.json`: bundled skill-pack inventory.
- `release-provenance.json`: project metadata, dependency declarations, and selected safe source hashes.
- `policy.yaml`: optional reviewed policy file when `--policy` is supplied.
- `provider-audit.json`: optional redacted provider inventory and policy audit when `--include-provider-audit` is supplied.

ZIP entries use fixed timestamps and sorted names to avoid unnecessary artifact churn. The bundle can be attached to benchmark reports or reviewed before running a paid remote matrix.

## Security Properties

Evidence bundles exclude provider configs, API keys, environment variables, keyring values, raw provider payloads, raw traces, run result rows, and dashboard state. When `--include-provider-audit` is used, the bundle includes only redacted provider audit metadata such as endpoint hosts, secret backend kind, TLS state, and policy findings. Including a policy file is intentional because policy is a reviewed governance artifact and should not contain raw secrets.
