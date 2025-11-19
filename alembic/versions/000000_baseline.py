"""baseline: adopt current DB schema as starting point

Revision ID: 000000_baseline
Revises:
Create Date: 2025-11-14 00:00:00.000000
"""

# revision identifiers, used by Alembic.
revision = "000000_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # baseline no-op: the DB already matches desired schema
    pass


def downgrade():
    pass
