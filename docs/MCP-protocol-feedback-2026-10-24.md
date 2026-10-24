I want to add a physical-device data point, because authorization + a signed execution receipt still leaves a third question: **did the external world actually change?**

In a small supervisor integration test with a mineflayer-based MCP server, `tools/call` returned success for movement and chat, but independent state reads showed different things:

- `move`: the state read immediately after the call was stale; after the next server tick it matched the tool's claimed position. So this was a fact-propagation delay, not a false claim.
- `chat`: the only observable confirmation was the server's local outgoing buffer, not a server-side echo. There was no independent fact to cite.
- `tools/list` had no `stop` / `estop` / `cancel` primitive; `chat("stop")` is just a message, not an action cancellation.

I don't think this is a bug report against that particular server. It illustrates a protocol-level distinction:

> a receipt proves what the server says it executed; it does not prove the device postcondition.

A signed receipt is valuable, but for physical tools it may need a companion **execution fact** (resource URI or postcondition) and an explicit cancellation/safe-state contract.

Questions for the group:

1. Should execution facts be distinct from signed receipts, or can a receipt carry a postcondition reference?
2. Is there appetite for optional tool capabilities such as `cancel`, `estop`, and `facts` (similar in spirit to existing annotations), without making them core requirements?
3. For cancellation, would a terminal `cancelled` / `safe_state` response be enough, or does this need a separate notification contract?

I'm not proposing that MCP absorb device-specific safety semantics. I'm trying to understand whether a small companion profile or SEP is the right place. Happy to share the probe and exact reproduction if useful.

---

Posted at:

https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/3215#discussioncomment-19159765

Scope: protocol-level completion facts and stop semantics. Not a report against
a specific MCP server, and not a security vulnerability disclosure.
