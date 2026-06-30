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

import logging
from typing import List, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, ConfigDict

from app.config import settings

logger = logging.getLogger(__name__)


def _load_public_key() -> str:
    with open(settings.JWT_PUBLIC_KEY_FILE, "r") as f:
        return f.read()


# Loaded once at import time. Fails fast if the key file is missing or unreadable.
_PUBLIC_KEY: str = _load_public_key()

_bearer = HTTPBearer(auto_error=True)


def base_tenant(tenant: str) -> str:
    """Map a tenant id to the stem tenant used for document storage.

    GEA sub-communities carry a sub-number in their tenant id
    ("GC106668-003"), but the filestore groups all sub-communities of a GEA
    under the stem tenant (the rcNumber, "GC106668"): storages, containers and
    files are stored under that stem. Strip the sub-number so storage lookups
    and the tenant check use the stem form. Non-GEA tenants have no dash and
    are returned unchanged.
    """
    return (tenant or "").split("-", 1)[0]


class Claims(BaseModel):
    tenants: List[str] = Field(default_factory=list, alias="tenant")
    preferred_username: Optional[str] = None
    realm_access: dict = Field(default_factory=dict)

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @property
    def roles(self) -> List[str]:
        return (self.realm_access or {}).get("roles", []) or []

    def is_superuser(self) -> bool:
        # Mirrors eegfaktura-backend: the realm role "superuser" grants
        # cross-tenant access and skips the tenant-claim membership check
        # (see api/middleware/tokenVerifier.go). Case-sensitive, like the backend.
        return "superuser" in self.roles

    def assert_tenant(self, tenant: str) -> None:
        if self.is_superuser():
            return
        wanted = base_tenant(tenant).upper()
        allowed = {base_tenant(t).upper() for t in self.tenants}
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
            audience=settings.JWT_AUDIENCE,
            options={"require": ["exp"]},
        )
    except jwt.PyJWTError as e:
        logger.warning("JWT decode failed: %s: %s", type(e).__name__, e)
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
