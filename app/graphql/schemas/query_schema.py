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

from fastapi import Request, WebSocket
from pydantic import typing
from strawberry import BasePermission
from strawberry.types import Info

from app.graphql.scalars.attribute_scalar import AttributeInput
from app.graphql.scalars.file_scalar import File

from app.graphql.resolvers.file_resolver import get_files
from app.graphql.resolvers.file_resolver import get_file




@strawberry.type
class Query:

    @strawberry.field
    async def files(self,
                    info: Info,
                    tenant: str,
                    attributes: typing.Optional[typing.List[AttributeInput]] = None,
                    category: typing.Optional[str] = "",
                    user_id: typing.Optional[uuid.UUID] = None,
                    limit: typing.Optional[int] = 10,
                    offset: typing.Optional[int] = 0)\
            -> typing.Optional[typing.List[File]]:
        """ get all Files
        :param info:
        :param tenant: Community id to get files for
        :param attributes: attributes to filter
        :param category: file category to filter
        :param user_id: user id to get files for specific user
        :param limit: limit the amount of returned elements
        :param offset: result offset
        """

        files = await get_files(tenant, info, attributes, category, user_id, limit, offset)
        return files


    @strawberry.field
    async def invoices(self,
                       info: Info,
                       tenant: str,
                       user_id: uuid.UUID,
                       attributes: typing.Optional[typing.List[AttributeInput]] = None,
                       limit: typing.Optional[int] = 10,
                       offset: typing.Optional[int] = 0)\
            -> typing.Optional[typing.List[File]]:
        """ get invoices for User
        :param info:
        :param tenant: Community id to get invoices for
        :param user_id: User id to get the invoices for
        :param attributes: attributes to filter
        :param limit: limit the amount of returned elements
        :param offset: result offset
        """

        files = await get_files(tenant, info, attributes, "invoice", user_id, limit, offset)
        return files


    @strawberry.field
    async def contracts(self,
                        info: Info,
                        tenant: str,
                        user_id: uuid.UUID,
                        attributes: typing.Optional[typing.List[AttributeInput]] = None,
                        limit: typing.Optional[int] = 10,
                        offset: typing.Optional[int] = 0)\
            -> typing.Optional[typing.List[File]]:
        """ get invoices for User
        :param info:
        :param tenant: Community id to get invoices for
        :param user_id: User id to get the invoices for
        :param attributes: attributes to filter
        :param limit: limit the amount of returned elements
        :param offset: result offset
        """

        files = await get_files(tenant, info, attributes, "contract", user_id, limit, offset)
        return files


    @strawberry.field
    async def file(self,
                   info: Info,
                   id: uuid.UUID)\
            -> typing.Optional[File]:
        """
        get file
        :param info:
        :param id: File UUID
        :return: File object
        """

        file = await get_file(id, info)
        return file

    @strawberry.field
    async def invoice(self,
                      info: Info,
                      id: uuid.UUID)\
            -> typing.Optional[File]:
        """
        get file
        :param info:
        :param id: File UUID
        :return: File object
        """

        file = await get_file(info, id, "invoice")
        return file

    @strawberry.field
    async def contract(self,
                       info: Info,
                       id: uuid.UUID)\
            -> typing.Optional[File]:
        """
        get file
        :param info:
        :param id: File UUID
        :return: File object
        """

        file = await get_file(info, id, "contract")
        return file

    @strawberry.field
    async def rc_contracts(self,
                           info: Info,
                           tenant: str,
                           attributes: typing.Optional[typing.List[AttributeInput]] = None,
                           limit: typing.Optional[int] = 10,
                           offset: typing.Optional[int] = 0) \
            -> typing.Optional[typing.List[File]]:
        """ get invoices for User
        :param info:
        :param tenant: Community id to get invoices for
        :param attributes: attributes to filter
        :param limit: limit the amount of returned elements
        :param offset: result offset
        """

        files = await get_files(tenant, info, attributes, "contract", None, limit, offset)
        return files