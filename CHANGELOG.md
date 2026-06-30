# Changelog

All notable changes to **eegfaktura-filestore (Python FastAPI file store)** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and
versioning follows the deployment release tags. Detailed diffs stay in the `git log`;
this changelog highlights the changes relevant for overview and operations.

## [Unreleased]

### Changed
- Upgrade the web/API stack: FastAPI 0.95→0.138, Starlette 0.26→1.3, Pydantic v1→v2
  (+ `pydantic-settings`), Strawberry GraphQL 0.172→0.320, uvicorn 0.21→0.49. Code migrated to
  pydantic v2 (`pydantic-settings.BaseSettings`, `Config`→`ConfigDict`) and to the new Strawberry
  union (`Annotated[Union[...], strawberry.union(name)]`) and `graphql_ide` router APIs. Validated
  end-to-end (schema build + authenticated GraphQL query) in the production base image. Supersedes
  the parked Dependabot majors #17 (starlette) and #21 (strawberry); no data/on-disk-format or
  GraphQL-schema changes.

### Fixed
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
