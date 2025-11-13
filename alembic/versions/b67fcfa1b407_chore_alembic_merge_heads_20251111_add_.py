"""chore(alembic): merge heads 20251111_add_is_admin and d1f2c3b4a5e6

Revision ID: b67fcfa1b407
Revises: 20251111_add_is_admin, d1f2c3b4a5e6
Create Date: 2025-11-13 13:46:48.823292

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "b67fcfa1b407"
down_revision: Union[str, Sequence[str], None] = (
    "20251111_add_is_admin",
    "d1f2c3b4a5e6",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
