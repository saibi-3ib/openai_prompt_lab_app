# name=alembic/versions/20251109_add_indexes_collectedpost.py url=https://github.com/saibi-3ib/openai_prompt_lab_app/blob/main/alembic/versions/20251109_add_indexes_collectedpost.py
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
    # Add indexes commonly used in filtering
    op.create_index(op.f('ix_collected_posts_username'), 'collected_posts', ['username'], unique=False)
    op.create_index(op.f('ix_collected_posts_posted_at'), 'collected_posts', ['posted_at'], unique=False)
    op.create_index(op.f('ix_collected_posts_like_count'), 'collected_posts', ['like_count'], unique=False)
    # Note: ticker_sentiment.ticker already has indexes in previous migrations

def downgrade():
    op.drop_index(op.f('ix_collected_posts_like_count'), table_name='collected_posts')
    op.drop_index(op.f('ix_collected_posts_posted_at'), table_name='collected_posts')
    op.drop_index(op.f('ix_collected_posts_username'), table_name='collected_posts')