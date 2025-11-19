"""merge merge_6605489abec3c2 and merge_66054e_c3c244e

Revision ID: ad758695d0ba
Revises: merge_6605489abec3c2, merge_66054e_c3c244e
Create Date: 2025-11-09 11:32:23.121125

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "ad758695d0ba"
down_revision: Union[str, Sequence[str], None] = (
    "merge_6605489abec3c2",
    "merge_66054e_c3c244e",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
