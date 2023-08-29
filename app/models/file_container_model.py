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
from typing import List
from typing import Any

from sqlalchemy import ForeignKey

from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

from sqlalchemy.sql import func, text


from . import Base


class FileContainer(Base):
    __tablename__ = "file_containers"
    __table_args__ = {'schema': 'filestore'}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(nullable=True)
    configuration: Mapped[dict[str, Any]] = mapped_column(nullable=True)

    file_category_id:  Mapped[uuid.UUID] = mapped_column(ForeignKey("filestore.file_categories.id"))
    file_category: Mapped["FileCategory"] = relationship(back_populates="file_containers")

    tenant: Mapped[str] = mapped_column(nullable=False)

    storage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("filestore.storages.id"))
    storage: Mapped["Storage"] = relationship(back_populates="file_containers")

    files: Mapped[List["File"]] = relationship(back_populates="file_container")

    def as_dict(self):
        return {
            "id": self.id,
            "name": self.name
        }
