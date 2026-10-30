# vfeeg-filestor File handling for eegFaktura
# Copyright (C) 2023  Matthias Poettinger
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

# Build-Stage: Compiler und libpq-Header nur hier (psycopg2 wird aus den Quellen gebaut).
# Die Pakete landen in einem venv, das die Laufzeit-Stage uebernimmt.
FROM python:3.13-slim-bookworm AS builder

RUN apt-get update && apt-get -y install --no-install-recommends libpq-dev gcc libc6-dev
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
COPY requirements.txt requirements.txt
RUN pip3 install --no-cache-dir --upgrade pip && pip3 install --no-cache-dir --upgrade -r requirements.txt

FROM python:3.13-slim-bookworm
LABEL org.vfeeg.vendor="Verein zur Förderung von Erneuerbaren Energiegemeinschaften"
LABEL org.vfeeg.image.authors="eegfaktura@vfeeg.org"
LABEL org.opencontainers.image.vendor="Verein zur Förderung von Erneuerbaren Energiegemeinschaften"
LABEL org.opencontainers.image.authors="eegfaktura@vfeeg.org"
LABEL org.opencontainers.image.title="eegfaktura-filestore"
LABEL org.opencontainers.image.description="EEG Faktura filestore service container handling the file upload and download"
LABEL org.opencontainers.image.licenses=AGPL-3.0
LABEL org.opencontainers.image.source=https://github.com/eegfaktura/eegfaktura-filestore
LABEL org.opencontainers.image.base.name=docker.io/python:3.13-slim-bookworm
LABEL description="EEG Faktura filestore service container handling the file upload and download"
LABEL version="0.1.0"

WORKDIR /vfeeg-filestore

# Laufzeit: nur die libpq-Bibliothek (psycopg2), kein Compiler, keine Header.
# Das pip des Basis-Images wird entfernt (bisher per Upgrade ersetzt); `pip` im PATH ist das
# aktualisierte pip im venv.
RUN apt-get update && apt-get -y upgrade && apt-get -y install --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m pip uninstall -y pip
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
COPY . .

# Non-root runtime user (Pod-Security-Admission "restricted" + Defense-in-Depth).
# /eegfaktura-filestore-data wird zur Laufzeit per PVC gemounted; das Helm-Chart
# muss `fsGroup: 1000` setzen, damit der gemountete Pfad fuer `app` schreibbar ist.
RUN groupadd -r app --gid 1000 \
    && useradd -r -g app --uid 1000 -d /vfeeg-filestore -s /sbin/nologin app \
    && chown -R app:app /vfeeg-filestore
USER app

# One JSON object per log line on stdout (LOG_LEVEL defaults to info)
ENV LOG_FORMAT="json"
ENV DB_HOSTNAME="postgres"
ENV DB_USERNAME="postgres"
ENV DB_DATABASE="eegfaktura"
ENV DB_PORT=5432
ENV HTTP_PROTOCOL="http"
ENV HTTP_HOSTNAME="0.0.0.0"
ENV HTTP_PORT=5000
ENV HTTP_FILE_DL_ENDPOINT="filestore"
ENV FILESTORE_LOCAL_BASE_DIR="/eegfaktura-filestore-data"

# service.version in the log; the release workflow passes the image version
ARG SERVICE_VERSION=dev
ENV SERVICE_VERSION=${SERVICE_VERSION}

EXPOSE ${HTTP_PORT}

# JWT-Pub-Key muss zur Laufzeit per Mount kommen — jwt_pub_key.pem ist
# aus dem Image entfernt (.dockerignore). Deploy setzt JWT_KEY_FILE
# z.B. auf /etc/jwt/pub.pem mit zugehörigem Secret-Mount. Ohne Datei
# scheitert der Container beim Start (app/auth.py, fail-fast).
CMD ["./entrypoint.sh"]
