"""Merge multiple heads into a single head

Revision ID: merge_6605489abec3c2
Revises: 66054e00253c,89abeef2a6d7,c3c244e4539d
Create Date: 2025-11-08 09:55:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'merge_6605489abec3c2'
down_revision = ('66054e00253c', '89abeef2a6d7', 'c3c244e4539d')
branch_labels = None
depends_on = None


def upgrade():
    # Merge migration: no schema changes. Its purpose is to unify multiple heads so
    # alembic upgrade head can proceed deterministically.
    pass


def downgrade():
    # No-op downgrade for merge revision.
    pass