# Session Persistence Notes

## Ground truth

ACP uses a client-created or client-reused session lifecycle. In practice with `acpx`, this is surfaced as:

- `acpx deepagents sessions new`
- `acpx deepagents sessions ensure`
- `acpx --approve-all deepagents prompt`

The same session must be reused across prompts.

Official references:

- ACP overview: https://agentclientprotocol.com/protocol/overview
- ACP session setup: https://agentclientprotocol.com/protocol/session-setup
- Deep Agents overview: https://docs.langchain.com/oss/python/deepagents/overview
- Deep Agents repository: https://github.com/langchain-ai/deepagents

## Local source confirmation

In the local ACP server implementation:

- `new_session()` generates a `session_id`
- `prompt()` passes that same `session_id` into LangGraph as `thread_id`

Relevant source:

- `${DEEPAGENTS_ACP_BASE_DIR}/deepagents_acp/server.py`

Key behavior:

- `new_session()` stores session metadata like cwd
- `prompt()` builds:

```python
config = {"configurable": {"thread_id": session_id}}
```

- if the agent has no checkpointer, it assigns `MemorySaver()`

This means:

- two prompts in the same ACP session share one Deep Agents thread
- a new ACP session means a new Deep Agents thread
- with `MemorySaver()`, persistence lasts only as long as the server process stays alive

## Practical implication for acpx

For continuous dialogue, you do not need a custom protocol extension. You need to:

1. keep using the same `acpx` session
2. avoid accidentally creating a fresh session
3. keep the local agent process alive long enough for follow-up prompts

That is why the project config uses `ttl: 0` and why named sessions are useful.

## OpenClaw mapping strategy

When OpenClaw is the outer conversation layer, the most practical way to preserve ACP continuity is:

1. read the current OpenClaw conversation identifier
2. deterministically map it to a named `acpx` session for each ACP agent
3. reuse that name on every follow-up turn

Recommended key choice:

- prefer `session_key`
- fallback to `session_id`

Recommended name shape:

```text
oc::<agent>::<short-hash-of-openclaw-session-identifier>
```

This avoids leaking raw internal identifiers into shell commands while still making the mapping deterministic.
