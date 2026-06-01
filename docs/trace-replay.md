# AgentBlaster Trace Replay

Trace replay lets a benchmark case provide explicit multi-turn context instead of a single synthesized user prompt. This is useful for agentic workflows where the interesting behavior depends on prior assistant tool calls, tool results, planning turns, or recovered session context.

## Case Shape

`BenchmarkCase.messages` is optional. If omitted, adapters continue to synthesize a single user message from `prompt` plus `system_prompt`.

Supported trace message roles:

- `system`: policy or instruction context.
- `user`: user turn or provider-specific user content blocks.
- `assistant`: assistant turn, optionally including OpenAI-style `tool_calls`.
- `tool`: deterministic tool result turn with `tool_call_id`.

Example:

```yaml
cases:
  - id: trace-replay-tool-result-summary
    title: Answer from replayed deterministic tool result
    prompt: Replay a prior tool-use conversation and answer from the tool result.
    messages:
      - role: system
        content: Answer from the provided tool result only.
      - role: user
        content: Read /repo/src/app.py and report the status string.
      - role: assistant
        content: ""
        tool_calls:
          - id: call_read_app
            type: function
            function:
              name: read_file_fixture
              arguments: '{"path":"/repo/src/app.py"}'
      - role: tool
        tool_call_id: call_read_app
        content: '{"content":"agentblaster-ok"}'
      - role: user
        content: What exact string was returned?
    expected_substring: agentblaster-ok
```

## Contract Mapping

- OpenAI Chat Completions receive the trace as `messages`.
- OpenAI Responses receives the trace as structured `input`.
- Anthropic Messages maps `system` messages to top-level `system`, assistant `tool_calls` to `tool_use` content blocks, and `tool` messages to user `tool_result` content blocks. When a case declares `cache_control`, Anthropic serialization can mark static system instructions and the final tool-catalog entry as cache breakpoints.
- Ollama native chat receives the trace as chat `messages`.

## Policy And Security

Enterprise prompt-size and cost ceilings include serialized trace messages. Trace replay does not execute host tools; it only replays already captured or deterministic tool-result content.
