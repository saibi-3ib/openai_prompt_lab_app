"""initial schema

Revision ID: 1929cc0687cd
Revises: 
Create Date: 2025-11-12 18:34:46.803950

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "1929cc0687cd"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    """Check whether table_name exists in the current DB connection."""
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    bind = op.get_bind()

    # prompts
    if not _table_exists(bind, "prompts"):
        op.create_table(
            "prompts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("template_text", sa.Text(), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )
        with op.batch_alter_table("prompts", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_prompts_id"), ["id"], unique=False)

    # settings
    if not _table_exists(bind, "settings"):
        op.create_table(
            "settings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("key", sa.String(), nullable=False),
            sa.Column("value", sa.String(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("settings", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_settings_key"), ["key"], unique=True)

    # stock_ticker_map
    if not _table_exists(bind, "stock_ticker_map"):
        op.create_table(
            "stock_ticker_map",
            sa.Column("ticker", sa.String(length=10), nullable=False),
            sa.Column("company_name", sa.String(), nullable=False),
            sa.Column("gics_sector", sa.String(), nullable=True),
            sa.Column("gics_sub_industry", sa.String(), nullable=True),
            sa.PrimaryKeyConstraint("ticker"),
        )
        with op.batch_alter_table("stock_ticker_map", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_stock_ticker_map_company_name"),
                ["company_name"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_stock_ticker_map_gics_sector"),
                ["gics_sector"],
                unique=False,
            )

    # target_accounts
    if not _table_exists(bind, "target_accounts"):
        op.create_table(
            "target_accounts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(), nullable=False),
            sa.Column("provider", sa.String(length=20), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("added_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("target_accounts", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_target_accounts_id"), ["id"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_target_accounts_provider"), ["provider"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_target_accounts_username"), ["username"], unique=True
            )

    # users
    if not _table_exists(bind, "users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(length=64), nullable=False),
            sa.Column("password_hash", sa.String(length=256), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("users", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_users_username"), ["username"], unique=True
            )

    # analysis_results
    if not _table_exists(bind, "analysis_results"):
        op.create_table(
            "analysis_results",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("prompt_id", sa.Integer(), nullable=False),
            sa.Column("raw_json_response", sa.Text(), nullable=True),
            sa.Column("extracted_summary", sa.Text(), nullable=True),
            sa.Column("analyzed_at", sa.DateTime(), nullable=True),
            sa.Column("ai_model", sa.String(), nullable=True),
            sa.Column("cost_usd", sa.Float(), nullable=True),
            sa.Column("input_tokens", sa.Integer(), nullable=True),
            sa.Column("output_tokens", sa.Integer(), nullable=True),
            sa.Column("extracted_tickers", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(
                ["prompt_id"],
                ["prompts.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("analysis_results", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_analysis_results_extracted_tickers"),
                ["extracted_tickers"],
                unique=False,
            )
            batch_op.create_index(
                batch_op.f("ix_analysis_results_id"), ["id"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_analysis_results_prompt_id"), ["prompt_id"], unique=False
            )

    # collected_posts
    if not _table_exists(bind, "collected_posts"):
        op.create_table(
            "collected_posts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(), nullable=False),
            sa.Column("post_id", sa.String(), nullable=False),
            sa.Column("original_text", sa.Text(), nullable=False),
            sa.Column("source_url", sa.String(), nullable=False),
            sa.Column("posted_at", sa.DateTime(), nullable=False),
            sa.Column("like_count", sa.Integer(), nullable=True),
            sa.Column("retweet_count", sa.Integer(), nullable=True),
            sa.Column("ai_summary", sa.Text(), nullable=True),
            sa.Column("link_summary", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["username"],
                ["target_accounts.username"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("collected_posts", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_collected_posts_id"), ["id"], unique=False
            )
            batch_op.create_index(
                batch_op.f("ix_collected_posts_post_id"), ["post_id"], unique=True
            )
            batch_op.create_index(
                batch_op.f("ix_collected_posts_username"), ["username"], unique=False
            )

    # user_ticker_weights
    if not _table_exists(bind, "user_ticker_weights"):
        op.create_table(
            "user_ticker_weights",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("account_id", sa.Integer(), nullable=False),
            sa.Column("ticker", sa.String(length=10), nullable=False),
            sa.Column("total_mentions", sa.Integer(), nullable=False),
            sa.Column("weight_ratio", sa.Float(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        with op.batch_alter_table("user_ticker_weights", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_user_ticker_weights_account_id"),
                ["account_id"],
                unique=False,
            )

    # ticker_sentiment
    if not _table_exists(bind, "ticker_sentiment"):
        op.create_table(
            "ticker_sentiment",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("ticker", sa.String(length=10), nullable=False),
            sa.Column("sentiment", sa.Float(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    # stock ticker map etc. (if there are additional tables later in the file, apply same pattern)
    # NOTE: If your original initial_schema file contains more table creation blocks beyond the shown ones,
    # apply the same existence-check pattern to each op.create_table and associated batch_alter_table.
    # ### end autogenerated commands ###
