# mini-claw-code

**[中文文档](./README-zh.md)**

Modular agent harness (`src/`) + upstream-style `skills/`.

This repository is a **minimal slice** of ideas from [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code): a **modular Python harness** in **`src/`**, plus the same **`skills/`** layout as upstream (on-demand `SKILL.md` loading via the `load_skill` tool).

**What this repo contains (by design):**

| Path | Purpose |
|------|---------|
| **`src/`** | Runnable harness: bootstrap, agent loop, REPL, tools, session/compact/cost, team bus, slash commands, optional experimental MCP bridge. |
| **`skills/`** | Example skill packs (`SKILL.md`) compatible with upstream’s skill-loading pattern. |
| Root | `README.md`, `README-zh.md`, `LICENSE`, `requirements.txt`, `.env.example`, `.gitignore`. |

**What is *not* shipped here** (stay on upstream if you need them):

- `agents/` (s01–s12 tutorials, `s_full.py`)
- `docs/` (course markdown)
- `web/` (Next.js learning site)

Clone or browse **[shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)** for the full learning path and documentation.

## Features (`src/`)

- **Modular layout**: `main.py`, `tools.py`, `session.py`, `team.py`, `commands.py`, optional `mcp_client.py`.
- **Session**: turn/token budgets, cost tracking, micro-compact, auto/manual summarization, JSON save/load.
- **Tool policy**: runtime deny by name or prefix (`ToolPermission`); `/permissions` in the REPL.
- **Concurrency helpers**: per-file locks for workspace writes and inbox files; global API semaphore when lead + teammates call the API.
- **Terminal UX**: color-coded tool vs final reply; teammate lines prefixed; wait for teammates/background tasks before the next `src >>` when appropriate.
- **Robustness**: UTF-8 file I/O on Windows; API retries with backoff; tool rounds keyed off **`tool_use` blocks**, not only `stop_reason`, for compatible gateways.
- **Optional MCP** (off by default): `--mcp` or `/mcp` — install `mcp` and `httpx` first.

## Install

```bash
pip install -r requirements.txt
```

**Optional (MCP):**

```bash
pip install mcp httpx
```

## Configure

```bash
cp .env.example .env
```

Set at least `ANTHROPIC_API_KEY` (or your provider’s key) and `MODEL_ID`. Optional: `ANTHROPIC_BASE_URL` for a proxy or third-party Messages-compatible endpoint.

## Run

```bash
python -m src.main
```

With MCP:

```bash
python -m src.main --mcp path/to/mcp_config.json
```

Use `/help` in the REPL for slash commands.

## License

MIT (aligned with upstream).
