# Capability Surface Catalogs

AgentBlaster can list bundled benchmark capability surfaces without launching providers or executing tools. Use these catalogs during enterprise policy review, suite approval, and report governance.

## Commands

```bash
agentblaster catalog simulated-tools
agentblaster catalog mcp-profiles
agentblaster catalog skills
```

Each command also supports JSON output:

```bash
agentblaster catalog simulated-tools --output-json reports/simulated-tools-catalog.json
agentblaster catalog mcp-profiles --output-json reports/mcp-profiles-catalog.json
agentblaster catalog skills --output-json reports/skills-catalog.json
```

## What The Catalogs Mean

- Simulated tools are deterministic AgentBlaster fixtures. They emulate search, file, shell, browser, and MCP-style behavior without touching the host filesystem, launching shell commands, opening browsers, or making network requests.
- MCP profiles are deterministic fixture catalogs that expand into OpenAI-compatible tool schemas. They are prompt and schema pressure tests, not live MCP server execution.
- Skill packs are bundled prompt-prefix fixtures used to test repeated static prefix pressure and agent workflow instruction following.

Every catalog item includes `host_execution: false`. Future real host-tool or live MCP execution support must use separate policy gates and must not be silently mixed with these deterministic fixtures.

## Policy Review Workflow

1. Generate JSON catalogs for the AgentBlaster version under review.
2. Approve names into `allowed_simulated_tools`, `allowed_mcp_profiles`, and `allowed_skills` in `agentblaster.policy.yaml`.
3. Keep `allow_tool_schemas`, `allow_simulated_tools`, `allow_mcp_profiles`, and `allow_skills` disabled or restricted for untrusted benchmark suites.
4. Attach the catalogs and release provenance artifact to corporate benchmark evidence bundles when external reviewers need to understand what prompt/tool surfaces were available.
