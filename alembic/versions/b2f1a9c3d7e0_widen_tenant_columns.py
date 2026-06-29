"""widen tenant columns from varchar(8) to varchar(64)

The original schema defined community_id/tenant as VARCHAR(8) (only ever
holds 8-char community ids like GC106668). Sub-community tenants use a
suffixed id such as "GC106668-003" (12 chars) which exceeds VARCHAR(8),
so storage/container auto-creation on first upload failed with
StringDataRightTruncationError. Widen the three tenant columns.

Revision ID: b2f1a9c3d7e0
Revises: c40127f5c680
Create Date: 2026-06-29 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b2f1a9c3d7e0'
down_revision = 'c40127f5c680'
branch_labels = None
depends_on = None

_TABLES = ('storages', 'file_containers', 'files')


def upgrade() -> None:
    for table in _TABLES:
        op.alter_column(table, 'tenant',
                        existing_type=sa.VARCHAR(length=8),
                        type_=sa.String(length=64),
                        existing_nullable=False,
                        schema='filestore')


def downgrade() -> None:
    for table in _TABLES:
        op.alter_column(table, 'tenant',
                        existing_type=sa.String(length=64),
                        type_=sa.VARCHAR(length=8),
                        existing_nullable=False,
                        schema='filestore')
