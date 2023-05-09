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

import os

from pydantic import BaseSettings

class Settings(BaseSettings):
    APP_TITLE: str="VFEEG Filestore"
    APP_VERSION: str="0.0.1"
    APP_LOG_LEVEL: str="info"
    #Load Database config from ENV
    DB_HOSTNAME: str = os.environ.get("DB_HOSTNAME", "127.0.0.1")
    DB_USERNAME: str = os.environ.get("DB_USERNAME", "filestore")
    DB_PASSWORD: str = os.environ.get("DB_PASSWORD", "PLktbxj9jtmGeHwMDc6S")
    DB_DATABASE: str = os.environ.get("DB_DATABASE", "filestore")
    DB_PORT: int = int(os.environ.get("DB_PORT", 5432))
    DB_DSN: str = f"postgresql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOSTNAME}:{DB_PORT}/{DB_DATABASE}"
    #HTTP Server Vars
    HTTP_PROTOCOL: str = os.environ.get("HTTP_PROTOCOL", "http")
    HTTP_HOSTNAME: str = os.environ.get("HTTP_HOSTNAME", "localhost")
    HTTP_PORT: int = int(os.environ.get("HTTP_PORT", 5000))
    HTTP_BASE_URI: str = f"{HTTP_PROTOCOL}://{HTTP_HOSTNAME}:{HTTP_PORT}"
    HTTP_FILE_DL_ENDPOINT: str = os.environ.get("HTTP_FILE_DL_ENDPOINT", "filestore")
    HTTP_FILE_DL_BASE_URI: str = os.environ.get("HTTP_FILE_DL_BASE_URI", f"{HTTP_BASE_URI}/{HTTP_FILE_DL_ENDPOINT}")
    FILESTORE_LOCAL_BASE_DIR: str = os.environ.get("FILESTORE_LOCAL_BASE_DIR", "/vfeeg-filestore-data")
    FILESTORE_TEMP_DIR: str = os.environ.get("FILESTORE_TEMP_DIR", f"{FILESTORE_LOCAL_BASE_DIR}/tmp")
    FILESTORE_CREATE_UNKNOWN_CATEGORY: bool = bool(os.environ.get("FILESTORE_CREATE_UNKNOWN_CATEGORY", "false"))
    FILESTORE_CREATE_UNKNOWN_CONTAINER: bool = bool(os.environ.get("FILESTORE_CREATE_UNKNOWN_CONTAINER", "false"))
    FILESTORE_CREATE_UNKNOWN_STORAGE: bool = bool(os.environ.get("FILESTORE_CREATE_UNKNOWN_STORAGE", "false"))

    JWT_PUBLIC_KEY_FILE: str= os.environ.get("JWT_KEY_FILE", "jwt_pub_key.pem")
settings = Settings()

