"""Add provider column (nullable), seed missing target_accounts, then add FK safely

Revision ID: c3c244e4539d
Revises: 98ab5c1ef8be
Create Date: 2025-11-08 09:44:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c3c244e4539d'
down_revision = '98ab5c1ef8be'
branch_labels = None
depends_on = None


def upgrade():
    # 1) Add provider column if not exists (nullable for now)
    op.execute("""
    ALTER TABLE target_accounts
    ADD COLUMN IF NOT EXISTS provider VARCHAR(50);
    """)

    # 2) Fill provider for existing target_accounts rows that have NULL
    op.execute("""
    UPDATE target_accounts
    SET provider = 'X'
    WHERE provider IS NULL;
    """)

    # 3) Insert missing target_accounts for orphan usernames found in collected_posts.
    #    This is idempotent: only inserts usernames that do not already exist in target_accounts.
    #    Set is_active = false and added_at = now() as safe defaults for demo cleanup.
    op.execute("""
    INSERT INTO target_accounts (username, is_active, added_at, provider)
    SELECT DISTINCT cp.username, false, now(), 'X'
    FROM collected_posts cp
    LEFT JOIN target_accounts ta ON ta.username = cp.username
    WHERE cp.username IS NOT NULL AND ta.username IS NULL;
    """)

    # 4) Ensure UNIQUE index on username exists. It already exists in current schema (ix_target_accounts_username),
    #    but we add a conditional check to be safe in other environments.
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename='target_accounts' AND indexname='ix_target_accounts_username'
      ) THEN
        CREATE UNIQUE INDEX ix_target_accounts_username ON public.target_accounts(username);
      END IF;
    END
    $$;
    """)

    # 5) Create FK constraint on collected_posts(username) referencing target_accounts(username) if not exists.
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_type='FOREIGN KEY'
          AND table_name='collected_posts'
          AND constraint_name='collected_posts_username_fkey'
      ) THEN
        ALTER TABLE collected_posts
        ADD CONSTRAINT collected_posts_username_fkey
        FOREIGN KEY (username) REFERENCES target_accounts(username) ON DELETE CASCADE;
      END IF;
    END
    $$;
    """)

    # 6) Now provider can be made NOT NULL (we filled NULLs above).
    op.execute("""
    ALTER TABLE target_accounts
    ALTER COLUMN provider SET NOT NULL;
    """)


def downgrade():
    # Reverse: drop FK if exists, drop provider column if exists
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_type='FOREIGN KEY'
          AND table_name='collected_posts'
          AND constraint_name='collected_posts_username_fkey'
      ) THEN
        ALTER TABLE collected_posts DROP CONSTRAINT collected_posts_username_fkey;
      END IF;
    END
    $$;
    """)

    op.execute("""
    ALTER TABLE target_accounts DROP COLUMN IF EXISTS provider;
    """)