"""Add provider column to target_accounts (idempotent)

Revision ID: c3c244e4539d
Revises: 89abeef2a6d7
Create Date: 2025-11-08 14:31:38.424488

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c3c244e4539d"
down_revision = "89abeef2a6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema idempotently."""
    # Add provider column only if it does not exist.
    op.execute(
        """
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='target_accounts' AND column_name='provider'
      ) THEN
        ALTER TABLE target_accounts
        ADD COLUMN provider VARCHAR(20) DEFAULT 'X' NOT NULL;
      END IF;
    END
    $$;
    """
    )

    # Create index on provider if not exists.
    op.execute(
        """
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename='target_accounts' AND indexname='ix_target_accounts_provider'
      ) THEN
        CREATE INDEX ix_target_accounts_provider ON public.target_accounts (provider);
      END IF;
    END
    $$;
    """
    )


def downgrade() -> None:
    """Downgrade schema idempotently."""
    # Drop index if exists, then drop column if exists.
    op.execute(
        """
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename='target_accounts' AND indexname='ix_target_accounts_provider'
      ) THEN
        DROP INDEX IF EXISTS ix_target_accounts_provider;
      END IF;
    END
    $$;
    """
    )

    op.execute(
        """
    ALTER TABLE target_accounts DROP COLUMN IF EXISTS provider;
    """
    )
