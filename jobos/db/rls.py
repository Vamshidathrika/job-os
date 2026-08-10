"""Row-Level Security policies for JOBOS."""

import asyncpg

TENANT_TABLES = [
    "users",
    "tenants",
    "tenant_keys",
    "credentials",
    "cg_bullets",
    "matches",
    "applications",
    "people",
    "referral_sequences",
    "outbox",
    "agent_decisions",
    "tenant_company_universe",
    "action_queue",
]


def generate_rls_sql(table_name: str) -> list[str]:
    """Generate RLS SQL statements for a given table.

    Returned as separate statements (not one multi-statement string) because
    asyncpg's extended query protocol — used by both SQLAlchemy/alembic and
    asyncpg.Connection.execute() — rejects multiple commands in a single
    prepared statement.

    Args:
        table_name: Name of the table.

    Returns:
        list[str]: The SQL statements to apply RLS, in execution order.
    """
    if table_name in ("credentials", "tenant_keys", "tenant_company_universe"):
        col_name = "tenant_id"
    elif table_name == "users":
        col_name = "id"
    else:
        col_name = "user_id"

    # An unset tenant yields NULL and an empty-string tenant yields NULL via
    # NULLIF, so both compare to NULL (never true) and the row is filtered.
    # NULLIF is used rather than an `AND current_setting(...) <> ''` guard
    # because Postgres does not guarantee AND short-circuits — the planner is
    # free to evaluate the ''::uuid cast first, which errors out instead of
    # returning zero rows. A malformed (non-empty) tenant id still raises,
    # which is intended: that's a caller bug, not an empty context.
    return [
        f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;",
        f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;",
        f"DROP POLICY IF EXISTS tenant_isolation_policy ON {table_name};",
        f"""
        CREATE POLICY tenant_isolation_policy ON {table_name}
        USING (
            {col_name} = NULLIF(current_setting('jobos.tenant_id', true), '')::uuid
        );
        """,
    ]


async def apply_rls(conn: asyncpg.Connection) -> None:
    """Apply RLS to all tenant tables.

    Args:
        conn: The database connection.
    """
    for table_name in TENANT_TABLES:
        for statement in generate_rls_sql(table_name):
            await conn.execute(statement)
