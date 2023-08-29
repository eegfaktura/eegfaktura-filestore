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

import datetime
import uuid

import strawberry
from pydantic import Field
from pydantic import typing
from strawberry.file_uploads import Upload

from app.graphql.scalars.attribute_scalar import Attribute, AttributeInput


@strawberry.type
class File:
    id: uuid.UUID
    tenant: str
    user_id: typing.Optional[uuid.UUID]
    name: str
    file_category: str
    attributes: typing.Optional[typing.List[Attribute]]
    file_download_uri: str
    created_at: datetime.datetime


@strawberry.input
class AddFileInput:
    file: Upload
    tenant: str
    user_id: typing.Optional[uuid.UUID] = ""
    name: str
    file_category: str
    attributes: typing.Optional[typing.List[Attribute]] = Field(default_factory=list)


@strawberry.type
class AddFile:
    id: uuid.UUID
    user_id: typing.Optional[uuid.UUID] = ""
    name: str
    file_category: str
    attributes: typing.Optional[typing.List[Attribute]] = Field(default_factory=list)
    file_download_uri: typing.Optional[str] = ""
    created_at: datetime.datetime


@strawberry.type
class DeleteFile:
    id: uuid.UUID
    message: str ="File deleted"

@strawberry.type
class FileExists:
    message: str = "File with same name, category and username already exists for this community"


@strawberry.type
class AddFileError:
    message: str = ""

@strawberry.type
class DeleteFileError:
    message: str = ""

@strawberry.type
class FileNotFound:
    message: str = "File not found in this community"


@strawberry.type
class CommunityMissing:
    message: str = "Required community is missing"


@strawberry.type
class NameMissing:
    message: str = "Required name is missing"

@strawberry.type
class FileCategoryMissing:
    message: str = "Required file category is missing"

@strawberry.type
class FileCategoryWrong:
    message: str = "File category not found"

@strawberry.type
class NoFileContainerFound:
    message: str = "No container for community and filetype found"



AddFileResponse = strawberry.union(
    "AddFileResponse", [AddFile, AddFileError]
)

DeleteFileResponse = strawberry.union(
    "DeleteFileResponse", [DeleteFile, DeleteFileError]
)