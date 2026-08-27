import logging
from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def sync_schema() -> None:
    """`Base.metadata.create_all()` only creates tables that don't exist
    yet — it never alters a table that's already there, so adding a
    column to a model (as happens routinely as this project grows) does
    nothing for anyone with an existing database, and every query against
    that table then fails with "column ... does not exist". This project
    deliberately doesn't use a migration framework (see README), so patch
    that specific gap directly: for each table that already existed,
    ADD COLUMN anything the model has that the database doesn't.

    Safe to run every startup — a no-op once the schema has caught up.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all() will have made this one fresh and already correct

            existing_columns = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue

                ddl_type = column.type.compile(dialect=engine.dialect)
                stmt = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}'

                default_sql = None
                if column.default is not None and getattr(column.default, "is_scalar", False):
                    value = column.default.arg
                    if isinstance(value, bool):
                        default_sql = "TRUE" if value else "FALSE"
                    elif isinstance(value, (int, float)):
                        default_sql = str(value)
                    elif isinstance(value, str):
                        default_sql = "'" + value.replace("'", "''") + "'"

                if default_sql is not None:
                    stmt += f" DEFAULT {default_sql}"
                    if not column.nullable:
                        stmt += " NOT NULL"

                logger.warning("sync_schema: adding missing column %s.%s", table.name, column.name)
                conn.execute(text(stmt))
