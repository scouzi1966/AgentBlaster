SMOKE_SENTINEL = "agentblaster-ok"
SMOKE_SENTINEL_PROMPT = f"Return only this exact text and nothing else: {SMOKE_SENTINEL}"
SMOKE_SENTINEL_SYSTEM_PROMPT = (
    "You are a deterministic benchmark responder. Do not include reasoning, planning, "
    "markdown, code fences, JSON, or commentary. Output only the requested sentinel text."
)
SMOKE_SENTINEL_MAX_TOKENS = 64

