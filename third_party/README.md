# Third-party components

This directory contains license texts and notices for code, patches, runtime
dependencies, and names referenced by Cyberdyne Bridge.

The CBAP Kernel/protocol code is MIT-licensed (see the root `LICENSE`).  This
does **not** relicense third-party material.  Exact upstream terms are in
`third_party/licenses/`, and the human-readable inventory is
[`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).

## Categories

```text
vendored patch       a diff against upstream source; retains upstream license
runtime dependency   installed from npm/pip; not vendored in this repo
external process     separate program launched over MCP/HTTP/Unix socket
name/trademark       Minecraft, Mojang, Microsoft, DeepSeek, Qwen, etc.
```

## GPL boundary

The file:

```text
agents/mcp-mineflayer/driver/patches/mineflayer-mcp-place.patch
```

is a patch against `swaynos/mineflayer-mcp`, which is **GPL-3.0**.  The patch
is distributed under GPL-3.0 and is **not** part of the MIT-licensed CBAP
core.  Do not apply it to a proprietary fork and expect the result to remain
MIT.  The CBAP adapter talks to the MCP server as a separate stdio process;
it does not import upstream GPL code into the Kernel.

This notice is not legal advice.  If you redistribute a combined work, review
the GPL-3.0 terms with counsel.
