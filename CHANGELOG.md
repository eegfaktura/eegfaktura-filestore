# Changelog

All notable changes to **eegfaktura-filestore (Python FastAPI file store)** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and
versioning follows the deployment release tags. Detailed diffs stay in the `git log`;
this changelog highlights the changes relevant for overview and operations.

## [Unreleased]

### Security
- strawberry-graphql 0.320.0 → 0.327.2: closes PYSEC-2026-4303 (fixed in 0.326.1, the Trivy
  HIGH finding; a permission check returning an awaitable from a plain `def` passed as allowed)
  and PYSEC-2026-4302 (fixed in 0.327.2, found by pip-audit). The filestore uses no strawberry
  permission classes, and the breaking changes in between (removed `Extension` alias, schema
  directives, cache extension defaults, graphql-ws subscriptions) touch no API it uses. One
  visible change: since 0.322.1 a non-string variable value for a `UUID` argument (e.g.
  `file_id`, `user_id`) gets a standard GraphQL coercion error instead of an unhandled server
  error. strawberry 0.323.1 raised its minimum typing-extensions to 4.14.0; the pinned 4.15.0
  satisfies it, so no other pin changes. (platform#185)

## [1.0.7] – 2026-10-21

### Added
- Tests: a token with a wrong `aud` gets 401; a token with the realm role `superuser` reaches another
  tenant's files (download, list, upload); GEA sub-community tenants (`GCxxxxxx-00n`) and their stem
  (`GCxxxxxx`) reach the same files in both directions, another stem gets 403. (platform#185)
- Test: an HS256 token signed with the RS256 public key as HMAC secret (algorithm confusion) gets
  401. The test switches off PyJWT's own refusal of PEM keys as HMAC secrets, so it fails as soon as
  `get_claims` accepts HS256; the former HS256 test used an unrelated secret and would have passed
  either way. (platform#185)
- CI: the full job runs `alembic check` after `alembic upgrade head`. (platform#185)
- Tests (`tests/`, pytest with FastAPI's TestClient against the migrated PostgreSQL, run by the CI
  full job): requests without or with an invalid token (no `exp`, expired, HS256) get 401; a token
  of another tenant cannot upload, download or list (403); only the categories `contract` and
  `invoice` are accepted (REST and GraphQL); upload and download for the own tenant. Test
  dependencies are pinned in `requirements-test.txt`; the tests generate their own RSA keypair.
  (platform#185)
- CI: job "Lint" runs ruff with bug-finding rules only (`F`, `E7`, `B`; `ruff.toml`) and blocks.
  Its findings are fixed: unused and duplicate imports removed, a stray expression statement
  (`0`) removed, bare `except` → `except Exception`, `caching == True` → `caching`, and the two
  re-raised `HTTPException`s chain their cause (`from e`). No behaviour change. (platform#185)
- CI: `pr-checks.yml` on every pull request: byte-compile and import (unit), Alembic
  migrations against PostgreSQL and an application start (full); a check that requirements.txt pins
  every dependency (report-only at first, now blocking, see below).
- CI: `security-scan.yml` on every pull request, on pushes to the default branch and weekly:
  leaked secrets in the new commits (Gitleaks, Trivy), vulnerable dependencies (Trivy,
  OSV-Scanner) and misconfigurations (Trivy). For now the dependency and misconfiguration
  findings are only reported (`SCAN_FAIL_ON: none`) and do not block; leaked secrets fail.
- CI: every run keeps its scan and test results as artifacts for 30 days (`scan-*`,
  `test-results-<job>`, `known-errors-<job>`) for a CI report collector; the secret scan keeps
  outcomes and counts only.

### Changed
- CI full job and the local `docker-compose.yml` database: PostgreSQL 18.6 (`postgres:18.6-alpine`,
  pinned by digest) instead of 15.19 / `15-alpine`, the major all zones run; the workflow comment
  no longer calls 15 the production major. The compose volume is now mounted at
  `/var/lib/postgresql` (as the 18 image requires); a local volume with 15 data is not upgraded,
  recreate it (`docker compose down -v`; the database container does not start on the old volume, and `down -v` deletes its data — dump it first if needed). (platform#185)
- Image: no empty `DB_PASSWORD` default in the image environment any more (Trivy DS-0031); the
  password still comes from `DB_PASSWORD` (as in the gitops manifests) or `DB_PASSWORD_FILE`, which
  the entrypoint now exports. apt installs without recommended packages (DS-0029); `libc6-dev`,
  until now pulled in as a recommendation of `gcc`, is named explicitly. (platform#185)
- `requirements.txt` pins the transitive dependencies too, at the versions the image installed so
  far (the installed set is unchanged). The CI check "Requirements pinned" now blocks; its output
  artifact is `test-results-requirements` (was `known-errors-requirements`). (platform#185)

### Fixed
- GraphQL `addFile` with a default attribute key (`orig_file_name`, `file_extension`, `media_type`,
  `file_bytes`) in `attributes` is rejected before anything is written: no temporary file is left
  in `FILESTORE_TEMP_DIR` any more. The client gets the same error ("Forbidden Attribute"); the
  file row was already rolled back before. (platform#185)
- `alembic check` no longer reports four foreign keys as changed. The online migration environment
  now compares only the `filestore` schema, with the version table named as in the offline one
  (`filestore.alembic_version`, where it already was); the migrations themselves are unchanged.
  (platform#185)

## [1.0.6] – 2026-10-17

### Changed
- **File categories are a fixed list** (`contract`, `invoice`). A GraphQL upload with any other
  category is rejected ("Invalid file category"); before, it created a new global category when
  `FILESTORE_CREATE_UNKNOWN_CATEGORY` was on (it was on in production). The REST upload was already
  limited to these two.
- **Storage and container of a tenant are created on its first upload without a switch.** The
  tenant is asserted first, so a member token can only create its own community's storage (a
  superuser passes the check for any tenant, as before). This is what production already did with
  the flags on; with the flags off, the first upload of a new community failed.

### Fixed
- **The first upload of a new category no longer creates a second storage for the tenant.** The
  storage was only looked up through an existing container of the same category, so e.g. a first
  invoice next to existing contracts created another storage. Now the tenant's storage is reused
  (lowest id, so the choice is stable also for tenants that already have several).
- **Deleting a file uses the storage of the file's container.** It looked the storage up by tenant
  only; for a tenant with several storages it could build a wrong path, delete the DB row and leave
  the file on disk.
- **REST upload (`POST /filestore/upload/…`) no longer answers 500 after storing the file.** It
  removed a key `community_id` that no longer exists since the tenant rename; a client retrying on
  5xx stored the document again. Containers created via REST no longer carry the enum class name in
  their name.

### Removed
- Environment variables `FILESTORE_CREATE_UNKNOWN_CATEGORY`, `_CONTAINER` and `_STORAGE`. They are
  ignored if still set; remove them from deployments.

## [1.0.5] – 2026-10-17

### Fixed
- **Uploads into a new storage or container work again under the non-root image.** Since 1.0.4 the
  service runs as UID 1000 and created new directories with mode `0o660` (no x bit), so it could not
  enter them: the first upload into every new storage/container failed with `Permission denied`
  (production: 17 uploads between 09.10. and 16.10.2026). New directories are now created with `0o750`.
  Directories already created with `0o660` stay broken until fixed once on the volume
  (`find <data> -mindepth 1 -type d ! -perm -u+x -exec chmod 750 {} +`).

## [1.0.4] – 2026-10-04

### Security
- The image runs as a non-root user (`app`, UID/GID 1000) on a `python:3.13-slim-bookworm` base,
  and the JWT public key is no longer baked into the image. The data PVC therefore needs
  `fsGroup: 1000` in the deployment — set it **before** rolling out this image, otherwise the
  service can no longer write to its storage directory. (#28)
- PyJWT 2.13.0 → 2.15.0 (#34) and anyio 4.14.1 → 4.14.2 (#32). The critical PyJWT advisories
  (asymmetric key used as HMAC secret) were not reachable here — tokens are decoded with
  `algorithms=["RS256"]` only — but the update closes them regardless.

### Fixed
- `ErrorMessage` failed to build whenever `message` or `detail` was omitted: since the Pydantic v2
  migration (#23) optional fields need an explicit default, and both lacked one, so constructing
  the error response itself raised a `ValidationError`. Both now default to `None`.

### Added
- CI builds `env/**` branches and deploys the resulting image into the matching feature
  environment (ADR-0008): a push to `env/<name>` pins this service in namespace `env-<name>`
  to that branch's `sha-…` image. Previously only the default branch, tags and `preview/**`
  produced an image at all. The environment itself is still provisioned manually.

## [1.0.3] – 2026-09-07

### Changed
- CI: Preview-Deployments (ADR-0007) — Push auf `preview/**` baut+deployt on-demand in die Dev-Zone (sha-pinned, kein `:latest`), Auto-Reset bei Branch-Delete.

## [1.0.2] – 2026-06-30

### Changed
- Upgrade the web/API stack: FastAPI 0.95→0.138, Starlette 0.26→1.3, Pydantic v1→v2
  (+ `pydantic-settings`), Strawberry GraphQL 0.172→0.320, uvicorn 0.21→0.49. Code migrated to
  pydantic v2 (`pydantic-settings.BaseSettings`, `Config`→`ConfigDict`) and to the new Strawberry
  union (`Annotated[Union[...], strawberry.union(name)]`) and `graphql_ide` router APIs. Validated
  end-to-end (schema build + authenticated GraphQL query) in the production base image. Supersedes
  the parked Dependabot majors #17 (starlette) and #21 (strawberry); no data/on-disk-format or
  GraphQL-schema changes.

### Fixed
- File uploads (`add_file`) returned `400 Unsupported content type` after the Strawberry 0.320
  upgrade: Strawberry disables GraphQL multipart uploads by default since ~0.236. Re-enable them
  on the `GraphQLRouter` (`multipart_uploads_enabled=True`). Verified end-to-end with a real
  multipart PDF upload (HTTP 200, file stored).
- Security: `FILESTORE_CREATE_UNKNOWN_*` flags were parsed with `bool(os.environ.get(..., "false"))`,
  where any non-empty string (including `"false"`) is truthy — so auto-creation of unknown
  storage/container/category was effectively always ON and could not be disabled via `false`.
  Parse with an explicit truthy-string check (`_env_bool`, default `False`). (#7)

## [1.0.1] – 2026-06-29

### Fixed
- Superuser cross-tenant access: mirror the backend `superuser` realm-role bypass so superusers can read/upload documents across communities. (#12)
- GEA stem tenant for document storage: normalize the tenant to its stem (rcNumber) so GEA sub-communities (e.g. `GC106668-003`) store and read under `GC106668`; fixes empty document lists and the `varchar(8)` upload error. (#13)

## [1.0.0] – 2026-06-28

Part of the unified source-build cutover of the eegfaktura suite.

### Changed
- CI: push to the registry's development tier (ADR-0005). (#6)
- Added README with service overview and tech stack. (#8)

## [0.x] – 2026-05

### Added
- JWT authentication and tenant enforcement for the GraphQL/REST endpoints.

### Fixed
- Download URI in the `add_file` resolver uses `db_file.id`. (#5)
- Auth: logs the specific PyJWT exception type and message. (#4)
- Auth: pass `audience` to PyJWT `decode` (config `JWT_AUDIENCE`). (#3)

### Security
- Bumped `pyjwt` to 2.12.1 (clears CVE-2026-32597).
