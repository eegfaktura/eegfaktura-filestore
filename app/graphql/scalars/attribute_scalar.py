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

import uuid

import strawberry
from pydantic import Field
from pydantic import typing


@strawberry.type
class Attribute:
    key: str
    value: typing.Optional[str] = ""

@strawberry.input
class AttributeInput:
    key: str
    value: typing.Optional[str] = ""

@strawberry.type
class AddAttribute:
    file_id: uuid.UUID
    key: str
    value: typing.Optional[str] = ""


@strawberry.type
class AttributeNotFound:
    message: str = "Attribute not found"


@strawberry.type
class FileIdMissing:
    message: str = "Required file id is missing"


@strawberry.type
class KeyMissing:
    message: str = "Required key is missing"


@strawberry.type
class AttributeDeleted:
    message: str = "Attribute successfully deleted"
