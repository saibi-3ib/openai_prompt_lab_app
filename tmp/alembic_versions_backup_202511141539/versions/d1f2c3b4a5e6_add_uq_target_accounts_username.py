"""add unique index on target_accounts.username

Revision ID: d1f2c3b4a5e6
Revises: ca92e7b381b0
Create Date: 2025-11-13 00:00:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "d1f2c3b4a5e6"
down_revision = "ca92e7b381b0"
branch_labels = None
depends_on = None


def upgrade():
    # Create a unique index on username.
    # Using an index (unique=True) is broadly supported, including SQLite.
    op.create_index(
        "ux_target_accounts_username",
        "target_accounts",
        ["username"],
        unique=True,
    )


def downgrade():
    op.drop_index("ux_target_accounts_username", table_name="target_accounts")
