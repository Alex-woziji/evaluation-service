# Database usage

This folder contains all DB-related code for evaluation-service.

## Backends

Use `.env` to choose backend:

- `DB_BACKEND=local` → local SQLite
- `DB_BACKEND=azure` → remote Azure DB (placeholder for now)

## Local SQLite setup

1. Set `.env`:
   - `DB_BACKEND=local`
   - `SQLITE_DB_PATH=data/evaluation.db`
2. Initialize DB:

```bash
python -m app.db
```

This creates the SQLite file and tables.

## Runtime checks

- If `DB_BACKEND=local`, app checks that `SQLITE_DB_PATH` exists.
  - If missing, app raises an error and asks you to run `python -m app.db`.
- If `DB_BACKEND=azure`, app checks `AZURE_DB_URL` is set and not mock placeholder.

## Env example

```env
DB_BACKEND=local
SQLITE_DB_PATH=data/evaluation.db
AZURE_DB_URL=mock://placeholder
OPENAI_API_KEY=sk-...
LOG_LEVEL=INFO
APP_VERSION=1.0.0
```
