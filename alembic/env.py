from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata


from app.models import Base
from app.models import File, FileCategory, FileAttribute, FileContainer, Storage
from app.config import settings

target_metadata = Base.metadata

config.set_main_option(
    "sqlalchemy.url", settings.DB_DSN)


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.



def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        version_table_schema='filestore',
        include_schemas=True,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"}
    )

    with context.begin_transaction():
        context.run_migrations()


def include_name(name, type_, parent_names) -> bool:
    # Compare only the filestore schema: the SET search_path below makes the unqualified schema point
    # at filestore too, comparing it as well would report every table twice.
    if type_ == "schema":
        return name == "filestore"
    return True


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        # Fixes the default schema SQLAlchemy reads on connect to public, whatever the database user is
        # called (a user named "filestore" would otherwise make filestore the default schema). Then
        # autogenerate/check reflect the filestore tables with their schema, as the models declare them.
        connect_args={"options": "-c search_path=public"},
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema='filestore',
            include_schemas=True,
            include_name=include_name,
        )

        with context.begin_transaction():
            context.execute(f"SET search_path TO filestore, public")
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
