from __future__ import annotations

from dataclasses import dataclass

from agentblaster.errors import ConfigError


@dataclass(frozen=True)
class LCPProfile:
    name: str
    title: str
    description: str
    context_bundle: str
    attachments: tuple[str, ...]
    host_execution: bool = False
    deterministic: bool = True


LCP_PROFILES: dict[str, LCPProfile] = {
    "fixture-lcp": LCPProfile(
        name="fixture-lcp",
        title="Fixture LCP context bundle",
        description="Synthetic local-context bundle with scoped memory, retrieval attachment metadata, and a sentinel fact.",
        attachments=("fixture://lcp/context-bundle", "fixture://lcp/session-memory", "fixture://lcp/retrieval/result-1"),
        context_bundle="""# AgentBlaster LCP Fixture

Profile: fixture-lcp
Scope: synthetic session-local context only
Host access: disabled
Network access: disabled
Raw local files: not attached

## Context Bundle Manifest

- bundle_id: lcp-fixture-context-bundle
- classification: public-fixture
- retention: benchmark-run-only
- redaction_required: true

## Scoped Session Memory

The user's local context contains a deterministic project status sentinel: agentblaster-lcp-ok.

## Retrieval Attachments

- attachment_id: lcp-retrieval-result-1
- uri: fixture://lcp/retrieval/result-1
- title: AgentBlaster local context fixture
- summary: Emerging LCP workflows must preserve context boundaries and answer only from attached fixture context.

Instruction: answer LCP fixture questions only from this context bundle.
""",
    ),
    "wide-lcp-context": LCPProfile(
        name="wide-lcp-context",
        title="Wide synthetic LCP context bundle",
        description="Large deterministic LCP-style context bundle for repeated-prefix and context-boundary stress tests.",
        attachments=("fixture://lcp/wide/context-bundle", "fixture://lcp/wide/session-memory"),
        context_bundle="\n".join(
            [
                "# AgentBlaster Wide LCP Fixture",
                "",
                "Scope: synthetic context bundle for prefill and cache diagnostics.",
                "Sentinel: agentblaster-lcp-ok",
                "Do not infer host filesystem, browser, or memory state beyond this bundle.",
                "",
                *[
                    f"LCP context rule {index:02d}: preserve scoped attachment boundaries and repeat the sentinel only when asked."
                    for index in range(1, 49)
                ],
            ]
        ),
    ),
}


def available_lcp_profiles() -> list[str]:
    return sorted(LCP_PROFILES)


def lcp_profile(name: str) -> LCPProfile:
    try:
        return LCP_PROFILES[name]
    except KeyError as exc:
        available = ", ".join(available_lcp_profiles())
        raise ConfigError(f"unknown LCP profile: {name}; available LCP profiles: {available}") from exc


def lcp_profile_text(name: str) -> str:
    profile = lcp_profile(name)
    return f"# AgentBlaster LCP context instructions\n\n{profile.context_bundle.strip()}"


def lcp_profile_catalog() -> list[dict[str, object]]:
    return [
        {
            "name": profile.name,
            "title": profile.title,
            "description": profile.description,
            "attachment_count": len(profile.attachments),
            "attachments": list(profile.attachments),
            "host_execution": profile.host_execution,
            "deterministic": profile.deterministic,
            "char_count": len(profile.context_bundle),
        }
        for profile in sorted(LCP_PROFILES.values(), key=lambda item: item.name)
    ]
