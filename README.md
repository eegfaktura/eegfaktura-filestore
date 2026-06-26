# eegfaktura-filestore

> Document/file storage service for the eegfaktura suite.

Stores and serves the suite's documents (e.g. invoices and contracts) together with
their metadata, via REST and GraphQL. Multi-tenant, with a hierarchical layout
(storage → category → container → file) keyed by UUIDs; access is protected by
RS256 JWT validation.

Part of the **eegfaktura** suite — an open-source billing and management platform
for Austrian renewable energy communities (*Erneuerbare-Energiegemeinschaften*, EEG).

## Tech stack

- **Python 3.10**, **FastAPI** + **Strawberry GraphQL**
- **SQLAlchemy 2** (async) + **asyncpg** over **PostgreSQL**; **Alembic** migrations
- **uvicorn** (ASGI); **PyJWT** (RS256); `aiofiles`

## Structure

- `app/` — `app.py` (FastAPI + GraphQL/REST wiring), `auth.py` (JWT validation),
  `config.py`, `models/` (Storage, FileCategory, FileContainer, File, FileAttribute),
  `graphql/`, `rest/routers/filestore.py`, `db/`
- Entry point: `main.py` (uvicorn on `:5000`); `entrypoint.sh` runs Alembic
  migrations, then starts the app

## Build / Run

```bash
pip install -r requirements.txt
python main.py        # or: uvicorn main:application --host 0.0.0.0 --port 5000
```

Docker / compose:

```bash
docker compose up     # entrypoint runs DB migrations first
```

## Configuration

Environment variables (names only — never commit secret values):

- `DB_HOSTNAME`, `DB_PORT`, `DB_USERNAME`, `DB_PASSWORD`, `DB_DATABASE`
- `HTTP_PROTOCOL`, `HTTP_HOSTNAME`, `HTTP_PORT` (default `5000`),
  `HTTP_FILE_DL_ENDPOINT`, `HTTP_FILE_DL_BASE_URI`
- `FILESTORE_LOCAL_BASE_DIR`, `FILESTORE_TEMP_DIR`
- `FILESTORE_CREATE_UNKNOWN_CATEGORY` / `_CONTAINER` / `_STORAGE` — auto-provisioning;
  **keep disabled in production**
- `JWT_KEY_FILE`, `JWT_AUDIENCE`
- `GRAPHIQL_ENABLED` — **disable in production**

Exposed port: **5000**. On-disk layout:
`{FILESTORE_LOCAL_BASE_DIR}/{storage_id}/{container_id}/{file_id}` (UUIDs only).

## Dependencies

- **PostgreSQL** — file metadata (schema `filestore`)
- **Keycloak** — RS256 public key for JWT validation
- On-disk storage volume

## License

GNU Affero General Public License v3.0 (AGPL-3.0) — see [`LICENSE`](LICENSE).
