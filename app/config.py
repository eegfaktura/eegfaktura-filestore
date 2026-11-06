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

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # a variable set but empty counts as not set (the defaults below and the APP_LOG_LEVEL fallback apply)
    model_config = SettingsConfigDict(env_ignore_empty=True)

    # The fields below up to the HTTP section are read from the environment by pydantic only (no
    # os.environ default next to it), so a Settings() made later, e.g. in a test, sees the same rules.
    # LOG_LEVEL: trace, debug, info, warn, error; the former APP_LOG_LEVEL is still read when LOG_LEVEL is not set
    LOG_LEVEL: str = Field("info", validation_alias=AliasChoices("LOG_LEVEL", "APP_LOG_LEVEL"))
    # LOG_FORMAT: json (the image sets it) or text (default when run from source)
    LOG_FORMAT: str = "text"
    SERVICE_VERSION: str = "dev"
    # deployment.environment on every log line (local, dev, pilot, prod); the field is left out when not set or blank
    DEPLOYMENT_ENVIRONMENT: str = ""
    #Load Database config from ENV
    DB_HOSTNAME: str = "127.0.0.1"
    DB_USERNAME: str = "filestore"
    DB_PASSWORD: str = ""
    DB_DATABASE: str = "filestore"
    DB_PORT: int = 5432

    @property
    def DB_DSN(self) -> str:
        return f"postgresql://{self.DB_USERNAME}:{self.DB_PASSWORD}@{self.DB_HOSTNAME}:{self.DB_PORT}/{self.DB_DATABASE}"

    #HTTP Server Vars
    HTTP_PROTOCOL: str = os.environ.get("HTTP_PROTOCOL", "http")
    HTTP_HOSTNAME: str = os.environ.get("HTTP_HOSTNAME", "localhost")
    HTTP_PORT: int = int(os.environ.get("HTTP_PORT", 5000))
    HTTP_BASE_URI: str = f"{HTTP_PROTOCOL}://{HTTP_HOSTNAME}:{HTTP_PORT}"
    HTTP_FILE_DL_ENDPOINT: str = os.environ.get("HTTP_FILE_DL_ENDPOINT", "filestore")
    HTTP_FILE_DL_BASE_URI: str = os.environ.get("HTTP_FILE_DL_BASE_URI", f"{HTTP_BASE_URI}/{HTTP_FILE_DL_ENDPOINT}")
    FILESTORE_LOCAL_BASE_DIR: str = os.environ.get("FILESTORE_LOCAL_BASE_DIR", "/vfeeg-filestore-data")
    FILESTORE_TEMP_DIR: str = os.environ.get("FILESTORE_TEMP_DIR", f"{FILESTORE_LOCAL_BASE_DIR}/tmp")

    JWT_PUBLIC_KEY_FILE: str= os.environ.get("JWT_KEY_FILE", "jwt_pub_key.pem")
    JWT_AUDIENCE: str = os.environ.get("JWT_AUDIENCE", "account")
    GRAPHIQL_ENABLED: bool = os.environ.get("GRAPHIQL_ENABLED", "false").lower() == "true"

    # here and not in the default above: the settings read the environment themselves
    @field_validator("DEPLOYMENT_ENVIRONMENT")
    @classmethod
    def _trim_deployment_environment(cls, value: str) -> str:
        return value.strip()

settings = Settings()

