# Capability Surface Catalogs

AgentBlaster can list bundled benchmark capability surfaces without launching providers or executing tools. Use these catalogs during enterprise policy review, suite approval, and report governance.

## Commands

```bash
agentblaster catalog simulated-tools
agentblaster catalog mcp-profiles
agentblaster catalog lcp-profiles
agentblaster catalog skills
```

Each command also supports JSON output:

```bash
agentblaster catalog simulated-tools --output-json reports/simulated-tools-catalog.json
agentblaster catalog mcp-profiles --output-json reports/mcp-profiles-catalog.json
agentblaster catalog lcp-profiles --output-json reports/lcp-profiles-catalog.json
agentblaster catalog skills --output-json reports/skills-catalog.json
```

## What The Catalogs Mean

- Simulated tools are deterministic AgentBlaster fixtures. They emulate search, file, shell, browser, and MCP-style behavior without touching the host filesystem, launching shell commands, opening browsers, or making network requests.
- MCP profiles are deterministic fixture catalogs that expand into OpenAI-compatible tool schemas. Fixture MCP calls can produce deterministic redaction-safe resource, tool, prompt, and wide-catalog results for assertions, but they are not live MCP server execution.
- LCP profiles are deterministic local-context fixture bundles. They emulate emerging local context attachment boundaries without reading host files, browser state, user memory, or network resources.
- Skill packs are bundled prompt-prefix fixtures used to test repeated static prefix pressure and agent workflow instruction following.

The built-in `agentic-tool-loop` suite combines these surfaces: deterministic explicit fixture tools, the `fixture-mcp` profile, the `fixture-lcp` context bundle, and bounded `max_tool_calls` cases that expose both successful final-response loops and max-tool-call boundary stops.

Every catalog item includes `host_execution: false`. Future real host-tool, live MCP, or real local-context provider support must use separate policy gates and must not be silently mixed with these deterministic fixtures.

## Policy Review Workflow

1. Generate JSON catalogs for the AgentBlaster version under review.
2. Approve names into `allowed_simulated_tools`, `allowed_mcp_profiles`, `allowed_lcp_profiles`, and `allowed_skills` in `agentblaster.policy.yaml`.
3. Keep `allow_tool_schemas`, `allow_simulated_tools`, `allow_mcp_profiles`, `allow_lcp_profiles`, and `allow_skills` disabled or restricted for untrusted benchmark suites.
4. Attach the catalogs and release provenance artifact to corporate benchmark evidence bundles when external reviewers need to understand what prompt/tool surfaces were available.
