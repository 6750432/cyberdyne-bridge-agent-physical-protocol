# Upstream feedback · mineflayer-mcp

## Status

**Blocked: upstream repository is archived.**  
GitHub rejected issue creation with:

```text
GraphQL: Repository was archived so is read-only (createIssue)
```

No issue was posted anywhere else. I did not bypass the archive or send email
without an explicit channel.

```text
repo:      swaynos/mineflayer-mcp
archived:  true
last push: 2026-05-08T02:26:09Z
```

## Prepared issue

**Title**:

```text
Question: is there a supported stop/estop path for in-flight actions?
```

**Body**:

```markdown
Hi — thanks for `mineflayer-mcp`.

I'm integrating this server behind an external supervisor that needs to cancel
in-flight navigation/actions. I may have missed a documented path, so I wanted
to ask before treating this as a feature request.

Environment:
- mineflayer-mcp package: 0.3.0
- `serverInfo.version`: 0.2.0
- Minecraft: 1.21.1
- transport: stdio

Observed:
`tools/list` exposes:
`observe, move, chat, dig, place, attack, use, inventory, status`

I could not find a `stop` / `estop` / `halt` / `cancel` tool or resource.
`chat("stop")` sends a message, but it does not cancel an in-flight action.

Impact:
If navigation or another action is in flight, an external supervisor has no
way to request a safe stop. That makes it hard to use this server where a
supervisor must guarantee cancellation.

Question:
Is stop/estop intentionally out of scope, or is there a recommended way to
cancel in-flight actions? If a small PR exposing a real stop path would be
welcome, I'm happy to help with the contract and tests.

Thanks.
```

## Do not

- Do not post this as a “fraud” or “vulnerability” claim.
- Do not put exploit details in a public issue.
- Do not email the maintainer without an explicit request.
- Do not reopen the same text on an unrelated fork as if it reached upstream.

## Next possible channels

1. The owner's explicit preferred channel, if they publish one.
2. An active maintained fork, only if the user explicitly chooses that target.
3. A private report for a confirmed security issue, through the target
   repository's security channel.
