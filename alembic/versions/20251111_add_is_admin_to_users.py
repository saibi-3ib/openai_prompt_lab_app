"""add is_admin to users

Revision ID: 20251111_add_is_admin
Revises: <PREV_REVISION_ID>
Create Date: 2025-11-11 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20251111_add_is_admin'
down_revision = '9675e53be358'
branch_labels = None
depends_on = None

def upgrade():
    # server_default を用いて既存行に false をセット
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.false()))
    # サーバデフォルトを追加した後、server_default を削除する場合は下記のようにする（オプション）
    # op.alter_column('users', 'is_admin', server_default=None)

def downgrade():
    op.drop_column('users', 'is_admin')