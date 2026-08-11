"""Integration tests for the `jobos token` CLI commands."""

import pytest

from jobos.cli import build_parser, run_token_command

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(autouse=True)
async def clean(db_pool, setup_schema):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM api_tokens")
    yield
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM api_tokens")


async def test_parser_exposes_token_subcommands():
    parser = build_parser()

    args = parser.parse_args(["--user-id", "u", "token", "create", "--name", "laptop"])
    assert args.command == "token"
    assert args.token_action == "create"
    assert args.name == "laptop"


async def test_create_returns_the_plaintext_once(db_pool, tenant_a_id):
    result = await run_token_command(
        db_pool, str(tenant_a_id), action="create", name="laptop"
    )

    assert result["token"].startswith("jobos_")
    assert "Store this now" in result["warning"]


async def test_list_never_returns_the_secret(db_pool, tenant_a_id):
    created = await run_token_command(
        db_pool, str(tenant_a_id), action="create", name="laptop"
    )

    listed = await run_token_command(db_pool, str(tenant_a_id), action="list")

    assert listed["tokens"][0]["name"] == "laptop"
    assert created["token"] not in str(listed)


async def test_revoke_reports_whether_it_found_one(db_pool, tenant_a_id):
    await run_token_command(db_pool, str(tenant_a_id), action="create", name="laptop")

    revoked = await run_token_command(
        db_pool, str(tenant_a_id), action="revoke", name="laptop"
    )
    assert revoked["revoked"] is True

    missing = await run_token_command(
        db_pool, str(tenant_a_id), action="revoke", name="never-existed"
    )
    assert missing["revoked"] is False
