"""baseline: adopt current DB schema as starting point

Revision ID: 5c85016089cd
Revises: 
Create Date: 2025-11-14 15:43:42.712207

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "5c85016089cd"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
