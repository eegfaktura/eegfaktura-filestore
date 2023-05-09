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

import strawberry
import uuid

from pydantic import typing
from strawberry.types import Info
from app.graphql.scalars.file_scalar import File

from app.graphql.resolvers.file_resolver import get_files
from app.graphql.resolvers.file_resolver import get_file
from app.graphql.resolvers.file_resolver import get_invoices
from app.graphql.resolvers.file_resolver import get_invoice


# TODO implement isAuthenticated Class
# https://strawberry.rocks/docs/guides/permissions#accessing-user-information


@strawberry.type
class Query:

    @strawberry.field
    async def files(self, info: Info, community_id: str, limit: typing.Optional[int] = 10) -> typing.List[File]:
        """ get all Files
        :param info:
        :param community_id: Community id to get files for
        :param limit: limit the amount of returned elements
        """

        files = await get_files(community_id, info, limit)
        return files

    @strawberry.field
    async def invoices(self, info: Info, community_id: str, user_id: uuid.UUID, limit: typing.Optional[int] = 10) -> typing.List[File]:
        """ get invoices for User
        :param info:
        :param community_id: Community id to get invoices for
        :param user_id: User id to get the invoices for
        :param limit: limit the amount of returned elements
        """
        try:
            files = await get_invoices(community_id, user_id, info, limit)
            return files
        except:
            return [None]

    @strawberry.field
    async def file(self, info: Info, id: uuid.UUID) -> typing.Optional[File]:
        """
        get file
        :param info:
        :param id: File UUID
        :return: File object
        """
        try:
            file = await get_file(id, info)
            return file
        except:
            return None

    @strawberry.field
    async def invoice(self, info: Info, id: uuid.UUID) -> typing.Optional[File]:
        """
        get file
        :param info:
        :param id: File UUID
        :return: File object
        """

        file = await get_invoice(id, info)
        return file
