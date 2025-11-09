"""Placeholder migration for missing revision 66054e00253c.

This is a NO-OP migration file created to satisfy Alembic's revision map parsing.
Please replace with the original migration from version control if/when available,
or remove this file after restoring the real migration history.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '66054e00253c'
# We don't know the original down_revision; set to None so this file will
# exist as a root revision. This avoids KeyError during revision map construction.
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # No changes; placeholder only
    pass

def downgrade() -> None:
    # No changes
    pass