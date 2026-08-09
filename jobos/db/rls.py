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
]


def generate_rls_sql(table_name: str) -> str:
    """Generate RLS SQL for a given table.

    Args:
        table_name: Name of the table.

    Returns:
        str: The SQL statements to apply RLS.
    """
    if table_name in ("credentials", "tenant_keys", "tenant_company_universe"):
        col_name = "tenant_id"
    elif table_name == "users":
        col_name = "id"
    else:
        col_name = "user_id"
    
    # Check current_setting('jobos.tenant_id', true) IS NOT NULL AND <col> = current_setting('jobos.tenant_id', true)::uuid
    policy_sql = f"""
        ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;
        
        DROP POLICY IF EXISTS tenant_isolation_policy ON {table_name};
        CREATE POLICY tenant_isolation_policy ON {table_name}
        USING (
            current_setting('jobos.tenant_id', true) IS NOT NULL 
            AND {col_name} = current_setting('jobos.tenant_id', true)::uuid
        );
    """
    return policy_sql


async def apply_rls(conn: asyncpg.Connection) -> None:
    """Apply RLS to all tenant tables.

    Args:
        conn: The database connection.
    """
    for table_name in TENANT_TABLES:
        sql = generate_rls_sql(table_name)
        await conn.execute(sql)
