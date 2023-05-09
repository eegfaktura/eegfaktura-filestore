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
from strawberry.file_uploads import Upload

from app.graphql.scalars.file_scalar import AddFileResponse
from app.graphql.resolvers.file_resolver import add_file

# TODO implement isAuthenticated Class
# https://strawberry.rocks/docs/guides/permissions#accessing-user-information


import strawberry


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def add_file(self, file: Upload, name: str, file_category: str, community_id: str, user_id: uuid.UUID = None) -> AddFileResponse:
        """ Add file """
        add_file_response = await add_file(file, name, file_category, community_id, user_id)
        return add_file_response

    @strawberry.mutation
    async def read_file(self, file: Upload) -> str:
        await file.read()
        return file.filename + " " + file.content_type
