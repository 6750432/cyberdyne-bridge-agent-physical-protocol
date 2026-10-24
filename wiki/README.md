# Wiki source

GitHub Wiki has no public API for the **first page**. A fresh wiki's
`.wiki.git` repository does not exist until one page is created in the web UI.

This directory contains the source for the index-only wiki:

```text
Home.md
_Sidebar.md
```

After the first page exists, push this folder to:

```text
git@github.com:cyberdyne-bridge/cyberdyne-bridge-agent-physical-protocol.wiki.git
```

Do not copy the full security/spec docs here; keep them in `README.md`,
`spec/`, and `docs/`.
