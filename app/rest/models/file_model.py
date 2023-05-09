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
from enum import Enum
from pydantic import BaseModel
from fastapi.responses import FileResponse



class FileCategoryEnum(str, Enum):
    invoice = "invoice"
    contract = "contract"


class FileUploadResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime.datetime
    file_category: FileCategoryEnum
    file_download_uri: str
