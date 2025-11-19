"""baseline: adopt current DB schema as starting point

Revision ID: 000000_baseline
Revises:
Create Date: 2025-11-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '000000_baseline'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # no-op baseline
    pass

def downgrade():
    pass
