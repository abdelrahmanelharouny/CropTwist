#!/usr/bin/env python3
"""Emit a deterministic schema inventory for clean-room database comparison.

Reads CROPTWIST_DATABASE_URL (the same setting Alembic uses). The snapshot
intentionally excludes row data and volatile PostgreSQL statistics.
"""
from __future__ import annotations

import json
import os
from sqlalchemy import create_engine, text, inspect


def main() -> None:
    url = os.environ.get("CROPTWIST_DATABASE_URL")
    if not url:
        raise SystemExit("CROPTWIST_DATABASE_URL is required")

    engine = create_engine(url, pool_pre_ping=True)
    try:
        inspector = inspect(engine)
        schema = "public"
        tables: list[dict[str, object]] = []
        for table_name in sorted(inspector.get_table_names(schema=schema)):
            columns = []
            for col in inspector.get_columns(table_name, schema=schema):
                columns.append({
                    "name": col["name"],
                    "type": str(col["type"]),
                    "nullable": bool(col["nullable"]),
                    "default": str(col["default"]) if col["default"] is not None else None,
                })
            tables.append({
                "name": table_name,
                "columns": columns,
                "primary_key": inspector.get_pk_constraint(table_name, schema=schema),
                "foreign_keys": sorted(
                    inspector.get_foreign_keys(table_name, schema=schema),
                    key=lambda item: (item.get("name") or "", str(item.get("constrained_columns"))),
                ),
                "unique_constraints": sorted(
                    inspector.get_unique_constraints(table_name, schema=schema),
                    key=lambda item: item.get("name") or "",
                ),
                "check_constraints": sorted(
                    inspector.get_check_constraints(table_name, schema=schema),
                    key=lambda item: item.get("name") or "",
                ),
                "indexes": sorted(
                    inspector.get_indexes(table_name, schema=schema),
                    key=lambda item: item.get("name") or "",
                ),
            })
        with engine.connect() as connection:
            extensions = [
                {"name": row[0], "version": row[1]}
                for row in connection.execute(
                    text("SELECT extname, extversion FROM pg_extension ORDER BY extname")
                )
            ]
        print(json.dumps({"schema": schema, "extensions": extensions, "tables": tables},
                         sort_keys=True, indent=2, default=str))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
