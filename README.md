# macro_foundry

An ambitious, long-running personal project to build the macroeconomic analysis stack I wish existed: a curated canonical database, an agent that grows it safely, nowcasting on top, and a frontend to drive it all.

## What it is

A canonical macro database designed for code and AI consumers, with the surrounding tooling to grow and use it. Series have semantic identifiers (`US_CPI_CORE_M_SA`) instead of provider tickers, every observation is vintage-tracked, and changes to the catalog are gated through a structured review workflow. On top of that foundation the eventual system includes a chat-style onboarding agent (runs end-to-end locally), a nowcasting layer, and a web frontend.

## Try it

```bash
git clone https://github.com/lckdairesearch/macro_foundry && cd macro_foundry
cp .env.example .env.local            # add MACRODB_*, FRED_API_KEY, OPENAI_API_KEY
docker compose --env-file .env.local up -d
uv sync && uv run alembic upgrade head
uv run macrodb seed --target dev
uv run macrodb db bootstrap fred-us-macro --target dev
uv run macrodb serve api --target dev
```

`--target dev` resolves to the local `macrodb_dev` database using the `macrodb_app` role (`MACRODB_APP_URL`). Target availability is command-specific; `prod` is never a CLI target. Migrations run as `macrodb_owner` via `MACRODB_OWNER_URL`.

Then open:
- **API docs** — http://127.0.0.1:8000/docs
- **Admin UI** — http://127.0.0.1:8000/admin

Run the test suite with `uv run pytest`.

### Try the onboarding agent

With the catalog seeded (above), open a chat-style onboarding session and describe a source in natural language:

```bash
uv run macrodb onboard --target dev --cost-cap 2.00
```

It needs `OPENAI_API_KEY` set and makes real LLM calls — `--cost-cap` is a hard spend limit. `/save` or Ctrl-D checkpoints and exits; resume with `uv run macrodb onboard --target dev --resume <session-id>`.

### Inspect the agent graphs in LangGraph Studio

To step through the onboarding graphs (`scope_series_onboarding`, `macrodb_chat`) visually with hot reload:

```bash
uv run langgraph dev
```

This starts the LangGraph API server on `http://127.0.0.1:2024` and opens LangGraph Studio in your default browser. Graphs and env are read from [langgraph.json](langgraph.json).

**Open Studio in a new Chrome window (instead of Safari).** `langgraph dev` opens via Python's `webbrowser`, which honours the `BROWSER` env var — but it splits `BROWSER` on whitespace, so the space in `/Applications/Google Chrome.app/...` can't be used directly. (Symlinking the binary doesn't work either: Chrome resolves its bundled framework relative to its executable path and crashes when launched through a symlink.) Create a small wrapper script that execs the real binary:

```bash
cat > /opt/homebrew/bin/chrome <<'EOF'
#!/bin/sh
exec "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" "$@"
EOF
chmod +x /opt/homebrew/bin/chrome
```

Then launch with `BROWSER` pointing at it:

```bash
BROWSER='chrome --new-window %s' uv run langgraph dev
```

`--new-window` makes Chrome open a fresh window (export the line in your shell profile to make it the default). Alternatively, set Chrome as your macOS default browser (System Settings → Desktop & Dock → Default web browser), or pass `--no-browser` to skip opening a browser entirely.

## Status

| Component | State |
|---|---|
| `macrodb` — curated database, FastAPI, SQLAdmin, seed, FRED bootstrap | Built and working locally; Neon parity next |
| Gated onboarding agent | Runs end-to-end locally — chat-style LangGraph session, custom MCP catalog server, real OpenAI calls (PRD [#32](https://github.com/lckdairesearch/macro_foundry/issues/32), ADRs 0011–0016) |
| Nowcasting | Planned; not started |
| Frontend | Planned; not started |

This is a single-operator project built in phases. The database is the foundation everything else lands on, so it gets built and stabilized first.

## Stack

Postgres 18 · async SQLAlchemy (psycopg3) · Alembic · FastAPI · SQLAdmin · Typer · uv

## Where to dig deeper

- [docs/project_overview.md](docs/project_overview.md) — what this is, in more depth
- [docs/architecture.md](docs/architecture.md) — the stack and the decisions behind it
- [CONTEXT.md](CONTEXT.md) — domain glossary (series vs concept vs observation, etc.)
- [docs/adr/](docs/adr/) — every architectural decision, with reasoning
- [docs/build_plan.md](docs/build_plan.md) and [docs/progress_tracker.md](docs/progress_tracker.md) — what's done and what's next

---

A single-operator research project. No public API, no SLA, no support. The code is the documentation; the ADRs are the rationale.
