# Contributing to YourDaaS

## Dev loop

```bash
cp .env.example .env
docker compose up --build -d        # full stack
cd web && npm install && npm run dev # front-end only (needs `computer` running)
```

## Conventions

- One logical change per commit; imperative subject (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `ci:`).
- No secrets in the repo — ever. Tokens and credentials live in `.env` (git-ignored) or the deployment host.
- Front-end expresses intent and renders state; orchestration, validation, and retries belong server-side (file API / container entrypoint).
- Keep UI copy minimal. If you add user-facing text, explain in the PR why it can't be removed or shown progressively.
- Local-first: every feature must run on `127.0.0.1` with zero cloud dependencies. Cloud (tunnel, R2, auth) is layered on, never required.

## Before opening a PR

- `docker compose up --build -d` from scratch works.
- New desktop defaults verified with a pristine home volume (`down -v`).
- `npm run build` passes in `web/`; new images build without cache surprises.
- Describe what changed, why, and how it was tested. For UI changes, attach a screenshot.
