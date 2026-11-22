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
        views = [
            {"name": name, "definition": inspector.get_view_definition(name, schema=schema)}
            for name in sorted(inspector.get_view_names(schema=schema))
        ]
        materialized_views = [
            {"name": name}
            for name in sorted(inspector.get_materialized_view_names(schema=schema))
        ]
        sequences = sorted(inspector.get_sequence_names(schema=schema))
        with engine.connect() as connection:
            migration_revisions = (
                sorted(connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all())
                if inspector.has_table("alembic_version", schema=schema)
                else []
            )
            extensions = [
                {"name": row[0], "version": row[1]}
                for row in connection.execute(
                    text("SELECT extname, extversion FROM pg_extension ORDER BY extname")
                )
            ]
            enums = [
                {"name": row[0], "labels": row[1]}
                for row in connection.execute(text("""
                    SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder)
                    FROM pg_type t
                    JOIN pg_enum e ON e.enumtypid = t.oid
                    JOIN pg_namespace n ON n.oid = t.typnamespace
                    WHERE n.nspname = 'public'
                    GROUP BY t.typname ORDER BY t.typname
                """))
            ]
            policies = [
                {
                    "table": row[0], "name": row[1], "permissive": row[2],
                    "roles": row[3], "command": row[4], "using": row[5],
                    "with_check": row[6],
                }
                for row in connection.execute(text("""
                    SELECT tablename, policyname, permissive, roles, cmd, qual, with_check
                    FROM pg_policies WHERE schemaname = 'public'
                    ORDER BY tablename, policyname
                """))
            ]
            triggers = [
                {"table": row[0], "name": row[1], "definition": row[2]}
                for row in connection.execute(text("""
                    SELECT c.relname, t.tgname, pg_get_triggerdef(t.oid, true)
                    FROM pg_trigger t
                    JOIN pg_class c ON c.oid = t.tgrelid
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND NOT t.tgisinternal
                    ORDER BY c.relname, t.tgname
                """))
            ]
        snapshot = {
            "schema": schema,
            "migration_revisions": migration_revisions,
            "extensions": extensions,
            "tables": tables,
            "views": views,
            "materialized_views": materialized_views,
            "sequences": sequences,
            "enums": enums,
            "row_level_security_policies": policies,
            "triggers": triggers,
        }
        print(json.dumps(snapshot, sort_keys=True, indent=2, default=str))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
