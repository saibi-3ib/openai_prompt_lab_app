"""Add indexes to collected_posts for filtering performance

Revision ID: 20251109_add_indexes_collectedpost
Revises: 
Create Date: 2025-11-09 00:00:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251109_add_indexes_collectedpost"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create indexes using op.create_index, guard with try/except so it's idempotent.
    try:
        op.create_index("ix_collected_posts_username", "collected_posts", ["username"])
    except Exception:
        pass

    try:
        op.create_index(
            "ix_collected_posts_posted_at", "collected_posts", ["posted_at"]
        )
    except Exception:
        pass

    try:
        op.create_index(
            "ix_collected_posts_like_count", "collected_posts", ["like_count"]
        )
    except Exception:
        pass


def downgrade():
    # Drop indexes if present
    try:
        op.drop_index("ix_collected_posts_username", table_name="collected_posts")
    except Exception:
        pass

    try:
        op.drop_index("ix_collected_posts_posted_at", table_name="collected_posts")
    except Exception:
        pass

    try:
        op.drop_index("ix_collected_posts_like_count", table_name="collected_posts")
    except Exception:
        pass
