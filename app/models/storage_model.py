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

from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.sql import func, text
from sqlalchemy.sql.functions import func

from . import Base

class Storage(Base):
    __tablename__ = "storages"
    __table_args__ = {'schema': 'filestore'}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))

    tenant: Mapped[str] = mapped_column(nullable=False)

    name: Mapped[str] = mapped_column(nullable=True)
    configuration: Mapped[dict[str, Any]] = mapped_column(nullable=True)

    file_containers: Mapped[List["FileContainer"]] = relationship(back_populates="storage")

    def as_dict(self):
        return {
            "id": self.id,
            "tenant": self.tenant,
            "name": self.name,
            "configuration": self.configuration
        }
