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

from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from sqlalchemy.sql import func, text

from sqlalchemy.dialects.postgresql import UUID


from . import Base

class FileAttribute(Base):
    __tablename__ = "file_attributes"
    file_id: Mapped[uuid] = mapped_column(ForeignKey("files.id"), primary_key=True)
    file: Mapped["File"] = relationship(back_populates="file_attributes")

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column()

    def as_dict(self):
        return {
            "file_id": self.file_id,
            "key": self.key,
            "value": self.value
        }
