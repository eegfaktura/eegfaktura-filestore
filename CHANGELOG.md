# Changelog

All notable changes to **eegfaktura-filestore (Python FastAPI file store)** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and
versioning follows the deployment release tags. Detailed diffs stay in the `git log`;
this changelog highlights the changes relevant for overview and operations.

## [Unreleased]

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
