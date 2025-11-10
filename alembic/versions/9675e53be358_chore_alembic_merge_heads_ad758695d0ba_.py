"""chore(alembic): merge heads ad758695d0ba and 20251109_add_indexes_collectedpost

Revision ID: 9675e53be358
Revises: ad758695d0ba, 20251109_add_indexes_collectedpost
Create Date: 2025-11-10 17:04:55.110922

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9675e53be358'
down_revision: Union[str, Sequence[str], None] = ('ad758695d0ba', '20251109_add_indexes_collectedpost')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
