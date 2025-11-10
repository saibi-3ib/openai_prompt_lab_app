"""Add indexes to collected_posts for filtering performance

Revision ID: 20251109_add_indexes_collectedpost
Revises: 
Create Date: 2025-11-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251109_add_indexes_collectedpost'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Use Postgres "IF NOT EXISTS" to avoid duplicate-index errors when index already present.
    conn = op.get_bind()
    # Create indexes if they do not already exist
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_collected_posts_username ON collected_posts (username)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_collected_posts_posted_at ON collected_posts (posted_at)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_collected_posts_like_count ON collected_posts (like_count)"))
    # Note: if you need other DB-agnostic behavior, handle conditionally here.

def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_collected_posts_like_count"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_collected_posts_posted_at"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_collected_posts_username"))