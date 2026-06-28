# Changelog

Alle nennenswerten Änderungen an **eegfaktura-filestore (Python FastAPI File-Store)** werden hier dokumentiert.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
die Versionierung an den Deployment-Release-Tags. Detail-Diffs bleiben im `git log`;
dieser Changelog hebt die für Überblick und Betrieb relevanten Änderungen hervor.

## [Unreleased]

## [1.0.0] – 2026-06-28

Teil des einheitlichen Source-Build-Cutovers der eegfaktura-Suite.

### Changed
- CI: Push in den Development-Tier der Registry (ADR-0005). (#6)
- README mit Service-Überblick und Tech-Stack ergänzt. (#8)

## [0.x] – 2026-05

### Added
- JWT-Authentifizierung und Tenant-Enforcement für GraphQL-/REST-Endpunkte.

### Fixed
- Download-URI im `add_file`-Resolver nutzt `db_file.id`. (#5)
- Auth: spezifischer PyJWT-Exception-Typ + Meldung werden geloggt. (#4)
- Auth: `audience` an PyJWT-`decode` übergeben (Konfig `JWT_AUDIENCE`). (#3)

### Security
- `pyjwt` auf 2.12.1 angehoben (behebt CVE-2026-32597).
