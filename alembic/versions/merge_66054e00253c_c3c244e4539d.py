"""Merge migration to join heads 66054e00253c and c3c244e4539d

This is a NO-OP merge revision that unifies the two heads so Alembic can
construct a single linear upgrade path. Replace with a proper merge revision
if you later recover the original missing migration file.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'merge_66054e_c3c244e'
down_revision: Union[str, Sequence[str], None] = ('66054e00253c', 'c3c244e4539d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # No schema changes here; this is a merge-only revision.
    pass

def downgrade() -> None:
    # No schema changes to revert.
    pass