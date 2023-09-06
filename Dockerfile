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

FROM python:3.10-slim-bullseye
LABEL org.vfeeg.vendor="Verein zur Förderung von Erneuerbaren Energiegemeinschaften"
LABEL org.vfeeg.image.authors="eegfaktura@vfeeg.org"
LABEL org.opencontainers.image.vendor="Verein zur Förderung von Erneuerbaren Energiegemeinschaften"
LABEL org.opencontainers.image.authors="eegfaktura@vfeeg.org"
LABEL org.opencontainers.image.title="eegfaktura-filestore"
LABEL org.opencontainers.image.description="EEG Faktura filestore service container handling the file upload and download"
LABEL org.opencontainers.image.licenses=AGPL-3.0
LABEL org.opencontainers.image.source=https://github.com/eegfaktura/eegfaktura-filestore
LABEL org.opencontainers.image.base.name=docker.io/python:3.10-slim-bullseye
LABEL description="EEG Faktura filestore service container handling the file upload and download"
LABEL version="0.1.0"

WORKDIR /vfeeg-filestore

COPY requirements.txt requirements.txt
RUN apt-get update && apt-get -y upgrade && apt-get -y install libpq-dev gcc
RUN pip3 install --no-cache-dir --upgrade pip && pip3 install --no-cache-dir --upgrade -r requirements.txt
#TEST ENV Only Debugging Tools
#RUN  apt-get install -y postgresql-client iputils-ping net-tools
COPY . .

ENV APP_LOG_LEVEL="debug"
ENV DB_HOSTNAME="postgres"
ENV DB_USERNAME="postgres"
ENV DB_PASSWORD=""
ENV DB_DATABASE="eegfaktura"
ENV DB_PORT=5432
ENV HTTP_PROTOCOL="http"
ENV HTTP_HOSTNAME="0.0.0.0"
ENV HTTP_PORT=5000
ENV HTTP_FILE_DL_ENDPOINT="filestore"
ENV FILESTORE_LOCAL_BASE_DIR="/eegfaktura-filestore-data"

EXPOSE ${HTTP_PORT}
CMD ["./entrypoint.sh"]
