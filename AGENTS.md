# AGENTS.md

## Cursor Cloud specific instructions

This repo contains **two independent products**:

1. **Next.js AI Chatbot** (repo root) — the Vercel Chat SDK. Primary product.
2. **Python AWS Lambda** — `lambda/sharepoint_csv_to_s3/` (SharePoint→S3 CSV ingestion). Unrelated to the chatbot.

Standard commands live in `package.json` `scripts` (`dev`, `build`, `lint`, `test`, `db:migrate`, etc.); use those. Notes below are the non-obvious caveats.

### Next.js chatbot — running it

- **Postgres is required** and is the only hard external service. It is not a codebase dependency, so it is installed at the system level (PostgreSQL 16) in the VM. Start the cluster each session (it does not auto-start):
  - `sudo pg_ctlcluster 16 main start`
  - Local DB used during setup: database `chatbot`, role `postgres`/`postgres` on `127.0.0.1:5432`.
- **`.env.local`** (gitignored) holds `AUTH_SECRET` and `POSTGRES_URL=postgres://postgres:postgres@127.0.0.1:5432/chatbot`. If it is missing on a fresh checkout, recreate it (generate `AUTH_SECRET` with `openssl rand -base64 32`).
- **Migrations are not in the update script.** After the DB is up, run `pnpm db:migrate` once (idempotent) before first use. `pnpm build` also runs migrations as a prestep.
- Run the dev server with `pnpm dev` (Turbopack). Health check: `GET /ping` → `pong`. Visiting `/` auto-creates a **guest** session (no login needed); `/register` and `/login` also work for real accounts.
- `REDIS_URL` (resumable streams) and `BLOB_READ_WRITE_TOKEN` (file uploads) are **optional** — the app degrades gracefully without them.
- **`AI_GATEWAY_API_KEY` is required for real model responses** (xAI via Vercel AI Gateway). Without it, auth, guest/registration, chat creation + DB persistence all work, but the streamed assistant reply will not be produced.

### Next.js chatbot — testing / lint caveats (important)

- **The Playwright suite (`pnpm test`) does not pass as-is on this branch** due to pre-existing app/test mismatches (not environment issues):
  - `lib/ai/models.mock.ts` emits a `text-delta` with no preceding `text-start`, which `ai@5.0.26` rejects (`"text part <id> not found"`), so streamed chat replies are empty in test mode.
  - The chat submit button no longer carries the `data-testid="send-button"` the tests rely on, so chat e2e tests hang on `page.goto('/')`/send.
  - The mock returns `"Mock response"`, but tests assert strings like `"It's just green duh!"`.
  - `app/(chat)/api/chat/route.ts` `onFinish` calls tokenlens `fetchModels()`, whose ~2.7MB catalog throws `Failed to set Next.js data cache, items over 2MB` in dev.
  - Note `doGenerate` (used for chat-title generation) works, so chats are still created with AI-generated titles even in test mode.
- **`pnpm lint` rewrites files** (`biome lint --write --unsafe`); it exits 0 by auto-fixing. For a read-only check use `pnpm exec biome lint ./`.
- First navigation to a route under `pnpm dev` triggers on-demand Turbopack compilation (~15s for `/`); warm it before tight test timeouts.

### Python lambda (`lambda/sharepoint_csv_to_s3/`)

- Install deps with `pip3 install -r lambda/sharepoint_csv_to_s3/requirements.txt` (also in the update script).
- It **cannot be run end-to-end locally**: it requires AWS Secrets Manager (`dev/sharepoint/hkgi`), SharePoint Online/Entra app-only creds, and an S3 bucket — all hardcoded in `handler.py` with no mocks. You can syntax-check/import (`python3 -c "import handler"`) and build the Lambda layer via `lambda/sharepoint_csv_to_s3/build-layer.sh` (needs Docker).
