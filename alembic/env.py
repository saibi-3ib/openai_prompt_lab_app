# alembic/env.py -- adapted to load Flask app and use Flask-SQLAlchemy metadata
from __future__ import with_statement

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import the Flask app factory and SQLAlchemy instance
# Adjust the import path if your create_app or extensions are located elsewhere.
from app import create_app
from app.extensions import db

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# If sqlalchemy.url is not set in alembic.ini, obtain it from Flask app config.
# Use FLASK_CONFIG environment variable if present (default to "development").
flask_config = os.getenv("FLASK_CONFIG", "development")
app = create_app(flask_config)

# Use the SQLAlchemy metadata from Flask-SQLAlchemy for autogenerate
target_metadata = db.metadata

# If alembic.ini doesn't contain sqlalchemy.url, set it from Flask app's engine.
if not config.get_main_option("sqlalchemy.url"):
    with app.app_context():
        # db.engine.url is a SQLAlchemy URL object; cast to str for alembic config.
        config.set_main_option("sqlalchemy.url", str(db.engine.url))


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
