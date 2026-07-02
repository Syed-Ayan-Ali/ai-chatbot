# AGENTS.md

## Cursor Cloud specific instructions

This repo is the **Vercel Chat SDK** — a Next.js (App Router) AI chatbot. Standard commands live in `package.json` `scripts` (`dev`, `build`, `lint`, `test`, `db:migrate`, etc.); use those. The notes below are the non-obvious caveats for running it in Cloud.

### Running the app

- **PostgreSQL is the only hard external dependency.** It is a system-level service (PostgreSQL 16), not a codebase dependency, so it is not installed by the update script. Start the cluster each session (it does not auto-start): `sudo pg_ctlcluster 16 main start`.
  - Local DB used during setup: database `chatbot`, role `postgres`/`postgres` on `127.0.0.1:5432`.
- **`.env.local`** (gitignored) holds `AUTH_SECRET` and `POSTGRES_URL=postgres://postgres:postgres@127.0.0.1:5432/chatbot`. If it is missing on a fresh checkout, recreate it (generate `AUTH_SECRET` with `openssl rand -base64 32`).
- **Migrations are not in the update script.** After the DB is up, run `pnpm db:migrate` once (idempotent) before first use. `pnpm build` also runs migrations as a prestep.
- Run the dev server with `pnpm dev` (Turbopack). Health check: `GET /ping` → `pong`. Visiting `/` auto-creates a **guest** session (no login needed); `/register` and `/login` also work for real accounts.
- `REDIS_URL` (resumable streams) and `BLOB_READ_WRITE_TOKEN` (file uploads) are **optional** — the app degrades gracefully without them.
- **`AI_GATEWAY_API_KEY` is required for real model responses** (xAI via Vercel AI Gateway). Without it, auth (guest/register/login), chat creation, and DB persistence all work, but the streamed assistant reply will not be produced.

### Lint / test caveats

- **`pnpm lint` rewrites files** (`biome lint --write --unsafe`) and exits 0 by auto-fixing. For a read-only check use `pnpm exec biome lint ./` (the repo currently has pre-existing style diagnostics under the read-only check).
- The Playwright suite (`pnpm test`) requires the dev server (`playwright.config.ts` starts `pnpm dev`) and generally needs `AI_GATEWAY_API_KEY` / mock-model behavior for chat assertions to pass; expect chat/e2e tests to be flaky without a working model provider.
- First navigation to a route under `pnpm dev` triggers on-demand Turbopack compilation (~a few seconds); warm it before tight test timeouts.
