# LCP Fixture Workflows

AgentBlaster includes fixture-only Local Context Protocol style workloads for emerging context-harness research. These fixtures model scoped context bundles, session-local memory, and retrieval attachment metadata without connecting to real host context providers.

## Profiles

- `fixture-lcp`: compact context bundle with a deterministic sentinel, scoped session memory, and one retrieval attachment.
- `wide-lcp-context`: larger repeated context bundle for prefill/cache and context-boundary pressure.

## Commands

```bash
agentblaster catalog lcp-profiles --output-json reports/lcp-profiles.json
agentblaster run --suite lcp-context --engine afm --model mlx-community/Qwen3.6-27B --offline --no-raw-traces
```

## Security Posture

LCP fixtures are bundled static text. They do not read local files, attach browser state, inspect memory, launch retrieval systems, call MCP servers, or contact remote APIs. Enterprise policy can block all LCP fixture injection with `allow_lcp_profiles: false` or restrict fixtures through `allowed_lcp_profiles`.
