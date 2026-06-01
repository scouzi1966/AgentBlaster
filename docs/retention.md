# AgentBlaster Retention Metadata

Every run manifest includes retention policy metadata so benchmark artifacts can be governed without inferring intent from folder names or cleanup history.

## CLI Usage

```bash
agentblaster run \
  --suite smoke \
  --engine afm \
  --model mlx-community/Qwen3.6-27B \
  --retention-classification confidential \
  --retention-days 30 \
  --raw-trace-retention-days 7 \
  --retention-note "delete raw traces before sharing"
```

Retention metadata is written to `manifest.json`:

```json
{
  "retention_policy": {
    "classification": "confidential",
    "retain_days": 30,
    "raw_trace_retain_days": 7,
    "notes": ["delete raw traces before sharing"]
  }
}
```

## Matrix Usage

Matrix entries can carry their own retention policy:

```yaml
name: qwen-gemma-local
runs:
  - engine: afm
    suite: trace-replay
    model: mlx-community/Qwen3.6-27B
    retention_policy:
      classification: confidential
      retain_days: 30
      raw_trace_retain_days: 7
      notes:
        - delete raw traces before sharing
```

If retention options are supplied on the `agentblaster run --matrix ...` command line, they override per-entry matrix retention metadata for that execution.

## Fields

- `classification`: `public`, `internal`, `confidential`, or `restricted`. Defaults to `internal`.
- `retain_days`: intended retention period for the run artifact directory.
- `raw_trace_retain_days`: intended retention period for raw trace artifacts, usually shorter than the full run.
- `notes`: operator guidance for cleanup, sharing, legal hold, or corporate retention systems.

## Cleanup

Retention metadata does not delete artifacts during benchmark execution. Use cleanup commands explicitly or wire manifest metadata into enterprise retention automation.

Plan expired cleanup without deleting anything:

```bash
agentblaster cleanup-expired --runs runs --output-json reports/cleanup-plan.json
```

Apply the planned cleanup actions:

```bash
agentblaster cleanup-expired --runs runs --execute --audit-log audit/control-plane.jsonl
```

Retention cleanup behavior:

- If `retain_days` is expired, the entire run directory is removed.
- If only `raw_trace_retain_days` is expired, only the run's `raw/` directory is removed.
- If both are expired, full run deletion wins.
- Runs without valid manifests are skipped.
- The command defaults to dry-run planning; deletion requires `--execute`.

Manual cleanup remains available:

```bash
agentblaster cleanup runs/<run-id> --raw --reports --exports
agentblaster cleanup runs/<run-id> --all-artifacts
```

Reports and publication JSON include the retention policy so reviewers can see whether an artifact bundle is suitable for sharing.

Retention metadata is included in `integrity.json` indirectly through the `manifest.json` checksum. If the retention policy is modified after a run, integrity verification will detect the manifest change.
