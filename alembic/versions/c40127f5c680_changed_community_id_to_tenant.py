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

"""Changed community_id to tenant

Revision ID: c40127f5c680
Revises: e7e81ce21ac0
Create Date: 2023-07-25 11:45:49.883051

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c40127f5c680'
down_revision = 'e7e81ce21ac0'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.alter_column('file_containers', 'community_id', nullable=False, new_column_name='tenant', schema='filestore')
    op.alter_column('files', 'community_id', nullable=False, new_column_name='tenant', schema='filestore')
    op.alter_column('storages', 'community_id', nullable=False, new_column_name='tenant', schema='filestore')


def downgrade() -> None:
    op.alter_column('file_containers', 'tenant', nullable=False, new_column_name='community_id', schema='filestore')
    op.alter_column('files', 'tenant', nullable=False, new_column_name='community_id', schema='filestore')
    op.alter_column('storages', 'tenant', nullable=False, new_column_name='community_id', schema='filestore')
