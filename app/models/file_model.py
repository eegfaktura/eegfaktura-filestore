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
from typing import List

from sqlalchemy import ForeignKey
from sqlalchemy.sql import func, text

from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from . import Base

class File(Base):
    __tablename__ = "files"
    __table_args__ = {'schema': 'filestore'}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(nullable=True)

    file_attributes: Mapped[List["FileAttribute"]] = relationship(back_populates="file")

    file_container_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("filestore.file_containers.id"))
    file_container: Mapped["FileContainer"] = relationship(back_populates="files")

    tenant: Mapped[str] = mapped_column(nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    def as_dict(self):
        return {
            "id": self.id,
            "tenant": self.tenant,
            "name": self.name,
            "file_container_id": self.file_container_id,
            "created_at": self.created_at
        }
