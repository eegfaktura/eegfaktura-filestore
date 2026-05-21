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

from typing import List, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.config import settings


def _load_public_key() -> str:
    with open(settings.JWT_PUBLIC_KEY_FILE, "r") as f:
        return f.read()


# Loaded once at import time. Fails fast if the key file is missing or unreadable.
_PUBLIC_KEY: str = _load_public_key()

_bearer = HTTPBearer(auto_error=True)


class Claims(BaseModel):
    tenants: List[str] = Field(default_factory=list, alias="tenant")
    preferred_username: Optional[str] = None

    class Config:
        allow_population_by_field_name = True
        extra = "ignore"

    def assert_tenant(self, tenant: str) -> None:
        wanted = (tenant or "").upper()
        allowed = {t.upper() for t in self.tenants}
        if wanted not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant not allowed",
            )


def get_claims(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> Claims:
    try:
        payload = jwt.decode(
            creds.credentials,
            _PUBLIC_KEY,
            algorithms=["RS256"],
            options={"require": ["exp"], "verify_aud": False},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    return Claims(**payload)


async def gql_context(
    request: Request,
    claims: Claims = Depends(get_claims),
) -> dict:
    return {"request": request, "claims": claims}
