from __future__ import annotations

from agentblaster.errors import ConfigError


SKILL_PACKS: dict[str, str] = {
    "repo-triage": """# Skill: repo-triage

Use a conservative repository triage workflow:

- Identify the smallest relevant file set before proposing edits.
- Prefer deterministic evidence from file contents and test output.
- Separate confirmed findings from assumptions.
- Produce a concise implementation plan before tool use.
""",
    "safe-tool-replay": """# Skill: safe-tool-replay

Use only benchmark-provided fixture tools.

- Do not request host filesystem, shell, browser, or network access.
- Treat tool outputs as deterministic replay fixtures.
- If fixture data is insufficient, report the missing fixture instead of inventing host state.
""",
    "agent-planning": """# Skill: agent-planning

Use a planner-worker loop for agentic tasks:

- Restate the objective in one sentence.
- Choose tools only when they reduce uncertainty.
- Keep intermediate state compact.
- Stop when the acceptance criteria are satisfied.
""",
    "large-prefix-diagnostic": "\n".join(
        [
            "# Skill: large-prefix-diagnostic",
            "",
            "This synthetic skill intentionally creates repeated static prefix pressure.",
            "Follow the benchmark instruction exactly and keep final answers short.",
            *[
                (
                    f"- Prefix diagnostic rule {index:02d}: preserve tool schemas, policy text, "
                    "and stable instructions across turns."
                )
                for index in range(1, 33)
            ],
        ]
    ),
}


def available_skill_packs() -> list[str]:
    return sorted(SKILL_PACKS)


def skill_pack_text(name: str) -> str:
    try:
        return SKILL_PACKS[name]
    except KeyError as exc:
        available = ", ".join(available_skill_packs())
        raise ConfigError(f"unknown skill pack: {name}; available skill packs: {available}") from exc


def skill_prefix(names: list[str]) -> str:
    if not names:
        return ""
    sections = [skill_pack_text(name).strip() for name in names]
    return "\n\n".join(["# AgentBlaster skill instructions", *sections]).strip()
