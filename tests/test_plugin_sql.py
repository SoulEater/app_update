"""SQL contracts using the official parser; no test-side database settings lookup.

Optional execution requires a LOCAL disposable fba_app_update_sql_test database.
Tests use a private transactional schema, never public or application tables.
"""

from __future__ import annotations

import csv
import json
import os
import re
import uuid

from pathlib import Path
from typing import TYPE_CHECKING

import anyio
import pytest

from backend.utils.sql_parser import parse_sql_script

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncConnection

SQL = Path(__file__).resolve().parents[1] / 'sql'
DIALECTS = ('mysql', 'postgresql')
MODES = ('', '_snowflake')
SCRIPTS = [
    SQL / dialect / f'{action}{mode}.sql' for dialect in DIALECTS for mode in MODES for action in ('init', 'destroy')
]
BASE_ID = 880210000000000
SeedValue = int | str | None


def menu_seeds(dialect: str, mode: str = '') -> list[list[SeedValue]]:
    source = (SQL / dialect / f'init{mode}.sql').read_text(encoding='utf-8')
    if dialect == 'mysql':
        match = re.search(r"SET @app_update_menus = '(.*?)';", source, re.DOTALL)
        assert match is not None
        return json.loads(match.group(1))
    block = source.split('FOR seed IN SELECT * FROM (VALUES', 1)[1].split(') AS s(', 1)[0]
    rows = []
    for line in block.splitlines():
        if not line.strip():
            continue
        line = line.strip().removesuffix(',').strip('()').replace('::bigint', '')
        row = next(csv.reader([line], quotechar="'", skipinitialspace=True))
        rows.append([None if value == 'NULL' else int(value) if value.isdigit() else value for value in row])
    return rows


@pytest.mark.anyio
@pytest.mark.parametrize(
    ['path'], [[path] for path in SCRIPTS], ids=[f'{path.parent.name}/{path.name}' for path in SCRIPTS]
)
async def test_official_parser_accepts_release_scripts(path: Path) -> None:
    statements = await parse_sql_script(str(path), is_destroy=path.name.startswith('destroy'))
    assert statements
    assert not any(statement.lstrip().startswith(('--', '/*')) for statement in statements)
    source = (await anyio.Path(path).read_text(encoding='utf-8')).lower()
    assert not re.search(r'\b(setval|random|rand|uuid|create|truncate)\s*\(', source)
    assert 'setval' not in source
    if path.name.startswith('init'):
        assert not re.search(r'\b(create|drop|alter|delete)\s+(table|index|from)', source)
    else:
        first = statements[0].lower()
        guard = 'raise exception' if path.parent.name == 'postgresql' else 'union all select json_array()'
        assert first.startswith('do' if path.parent.name == 'postgresql' else 'set')
        assert guard in first
        assert source.index(guard) < source.index('delete from')
        assert source.index('delete from sys_role_menu') < source.index('delete from sys_menu')
        assert 'parent_id' in first
        if path.parent.name == 'postgresql':
            assert 'parent_id = any(menu_ids) and not (id = any(menu_ids))' in first
            assert 'is not distinct from' in first
        else:
            assert 'join plugin_menus parent on child.parent_id = parent.id' in first
            assert 'left join plugin_menus own on child.id = own.id' in first
            assert 'where own.id is null' in first
            assert 'delete' not in first
            assert all(f'm.{field} <=> s.{field}' in first for field in ('path', 'component', 'perms'))
        assert re.findall(r'drop table if exists (\w+)', source) == [
            'app_update_artifact',
            'app_update_release',
            'app_update_channel',
            'app_update_application',
        ]
        assert 'cascade' not in source
        assert 'like' not in source


@pytest.mark.anyio
async def test_four_initializers_have_identical_menu_semantics() -> None:
    expected = await anyio.to_thread.run_sync(menu_seeds, 'mysql')
    assert len(expected) == 15
    assert len({row[2] for row in expected}) == 15
    for dialect in DIALECTS:
        for mode in MODES:
            rows = await anyio.to_thread.run_sync(menu_seeds, dialect, mode)
            assert [row[1:] for row in rows] == [row[1:] for row in expected]
            if mode:
                assert {row[0] for row in rows} == set(range(BASE_ID + 1, BASE_ID + 16))
                assert all(isinstance(row[0], int) and 0 < row[0] < 2**53 for row in rows)
    by_name = {row[2]: row for row in expected}
    assert by_name['PluginAppUpdate'][9] is None
    assert by_name['PluginAppUpdateReleases'][9] == 'PluginAppUpdate'
    assert by_name['PluginAppUpdateApplications'][9] == 'PluginAppUpdate'
    for row in expected[3:]:
        assert row[6] == 2
        expected_parent = (
            'PluginAppUpdateReleases' if str(row[2]).startswith('AppUpdateRelease') else 'PluginAppUpdateApplications'
        )
        assert row[9] == expected_parent
        assert str(row[8]).startswith('app_update:')


@pytest.mark.anyio
@pytest.mark.parametrize(['dialect'], [['mysql'], ['postgresql']])
async def test_destroy_whitelist_matches_seed_identities(dialect: str) -> None:
    source = await anyio.Path(SQL / dialect / 'destroy.sql').read_text(encoding='utf-8')
    snow = await anyio.Path(SQL / dialect / 'destroy_snowflake.sql').read_text(encoding='utf-8')
    assert source == snow
    seeds = await anyio.to_thread.run_sync(menu_seeds, dialect)
    expected = [[row[index] for index in (2, 6, 3, 7, 8)] for row in seeds]
    if dialect == 'mysql':
        block = source.split("JOIN JSON_TABLE('", 1)[1].split("', '$[*]'", 1)[0]
        actual = json.loads(block)
    else:
        block = source.split('JOIN (VALUES', 1)[1].split(') AS s(', 1)[0]
        actual = []
        for line in block.splitlines():
            if line.strip():
                text = line.strip().removesuffix(',').strip('()')
                row = next(csv.reader([text], quotechar="'", skipinitialspace=True))
                values = [None if value == 'NULL' else int(value) if value.isdigit() else value for value in row]
                actual.append(values)
    assert actual == expected


@pytest.mark.anyio
@pytest.mark.parametrize(['dialect'], [['mysql'], ['postgresql']])
async def test_primary_key_modes_have_distinct_allocation_contracts(dialect: str) -> None:
    auto = await anyio.Path(SQL / dialect / 'init.sql').read_text(encoding='utf-8')
    snow = await anyio.Path(SQL / dialect / 'init_snowflake.sql').read_text(encoding='utf-8')
    assert not re.search(r'880210\d+', auto)
    for table in ('app_update_application', 'app_update_channel'):
        assert not re.search(rf'INSERT INTO {table} \(id,', auto, re.IGNORECASE)
        assert re.search(rf'INSERT INTO {table} \(id,', snow, re.IGNORECASE)
    assert all(str(BASE_ID + offset) in snow for offset in (101, 102, 103))
    assert 'seed ID conflict' in snow or 'seed_conflict' in snow
    for source in (auto, snow):
        assert 'application_id = 1' not in source
        if dialect == 'mysql':
            # Three allocating inserts, then one existing-ID-only title synchronization.
            allocating = re.findall(r'INSERT INTO sys_menu .*?;', source, re.DOTALL)[:3]
            assert len(allocating) == 3
            for kind, statement in enumerate(allocating):
                assert f's.type = {kind}' in statement
                assert ('(id,' in statement) == bool(source == snow)
                if kind:
                    assert 'JOIN sys_menu p ON p.name = s.parent_name' in statement
                    assert 'NULL, p.id,' in statement
            assert 'coalesce(p.id' not in source
            assert 'SELECT m.id, s.title' in source  # Existing identity; never a new seed ID.
            assert 's.parent_name IS NOT NULL AND p.id IS NULL' in source
            assert 'c.application_id = a.id' in source
        else:
            assert ('INSERT INTO sys_menu (id,' in source) == bool(source == snow)
            assert 'SELECT id INTO STRICT parent' in source
            assert 'SELECT id INTO STRICT demo_id' in source
            assert 'existing.parent_id IS DISTINCT FROM parent' in source
            assert 'UPDATE sys_menu SET title = seed.title' in source


@pytest.mark.anyio
@pytest.mark.parametrize(['dialect'], [['mysql'], ['postgresql']])
@pytest.mark.parametrize(['mode'], [[''], ['_snowflake']])
async def test_manual_schema_is_retained_separately(dialect: str, mode: str) -> None:
    schema = (await anyio.Path(SQL / dialect / f'schema{mode}.sql').read_text(encoding='utf-8')).lower()
    assert re.findall(r'create table if not exists (\w+)', schema) == [
        'app_update_application',
        'app_update_channel',
        'app_update_release',
        'app_update_artifact',
    ]
    assert 'sys_menu' not in schema
    for constraint in ('channel_app_code', 'release_identity', 'artifact_release_kind'):
        assert f'uk_app_update_{constraint}' in schema
    if mode:
        assert 'bigserial' not in schema and 'auto_increment' not in schema
    else:
        assert schema.count('bigserial' if dialect == 'postgresql' else 'auto_increment') == 4


async def execute_statements(conn: AsyncConnection, statements: Sequence[str]) -> None:
    for statement in statements:
        await conn.exec_driver_sql(statement)


async def setup_postgresql_schema(conn: AsyncConnection, mode: str, statements: Sequence[str]) -> None:
    pk_type = 'bigint' if mode else 'bigserial'
    await conn.exec_driver_sql(f"""CREATE TABLE sys_menu (
        id {pk_type} PRIMARY KEY, title varchar(64) NOT NULL, name varchar(64) NOT NULL,
        path varchar(200), sort integer, icon varchar(128), type integer,
        component varchar(256), perms varchar(128), status integer, display integer,
        cache integer, link text, remark text, parent_id bigint,
        deleted bigint DEFAULT 0, created_time timestamptz, updated_time timestamptz
    )""")
    await conn.exec_driver_sql("""CREATE TABLE sys_role_menu (
        role_id bigint, menu_id bigint REFERENCES sys_menu(id), PRIMARY KEY (role_id, menu_id)
    )""")
    await execute_statements(conn, statements)
    await conn.exec_driver_sql(
        "INSERT INTO app_update_application (id, key, name) VALUES (42, 'demo', 'Existing demo')"
    )
    # A legacy root must retain its actual ID; missing pages/buttons must map to it.
    await conn.exec_driver_sql("""INSERT INTO sys_menu (id, title, name, path, type)
        VALUES (77, 'old', 'PluginAppUpdate', '/plugins/app-update', 0)""")


async def check_postgresql_repeat(conn: AsyncConnection, mode: str, init: Sequence[str]) -> None:
    for _ in range(2):
        await execute_statements(conn, init)
    assert (await conn.exec_driver_sql('SELECT count(*) FROM sys_menu')).scalar_one() == 15
    apps = await conn.exec_driver_sql('SELECT DISTINCT application_id FROM app_update_channel')
    assert apps.scalars().all() == [42]
    parents = await conn.exec_driver_sql('SELECT DISTINCT parent_id FROM sys_menu WHERE type = 1')
    assert parents.scalars().all() == [77]
    assert (await conn.exec_driver_sql('SELECT count(*) FROM app_update_channel')).scalar_one() == 2
    if not mode:
        maximum = (await conn.exec_driver_sql('SELECT max(id) FROM sys_menu')).scalar_one()
        assert maximum < 100


async def check_postgresql_partial_repair(conn: AsyncConnection, mode: str, init: Sequence[str]) -> None:
    async with conn.begin_nested() as savepoint:
        await conn.exec_driver_sql('DELETE FROM app_update_channel')
        await conn.exec_driver_sql('DELETE FROM app_update_application')
        await execute_statements(conn, init)
        demo = (await conn.exec_driver_sql('SELECT id FROM app_update_application')).scalar_one()
        if mode:
            assert demo == BASE_ID + 101
        else:
            assert demo < 100
        channels = await conn.exec_driver_sql('SELECT DISTINCT application_id FROM app_update_channel')
        assert channels.scalars().all() == [demo]
        await savepoint.rollback()
    async with conn.begin_nested() as savepoint:
        await conn.exec_driver_sql('DELETE FROM sys_menu WHERE type = 2')
        await conn.exec_driver_sql("DELETE FROM sys_menu WHERE name = 'PluginAppUpdateApplications'")
        await execute_statements(conn, init)
        assert (await conn.exec_driver_sql('SELECT count(*) FROM sys_menu')).scalar_one() == 15
        await savepoint.rollback()


async def check_postgresql_identity_conflicts(conn: AsyncConnection, init: Sequence[str]) -> None:
    async with conn.begin_nested() as savepoint:
        await conn.exec_driver_sql("UPDATE sys_menu SET parent_id = 77 WHERE name = 'AppUpdateChannelEdit'")
        with pytest.raises(Exception, match='app_update menu identity conflict'):
            await execute_statements(conn, init)
        await savepoint.rollback()
    await conn.exec_driver_sql("DELETE FROM sys_menu WHERE name = 'AppUpdateChannelEdit'")
    await execute_statements(conn, init)
    assert (await conn.exec_driver_sql('SELECT count(*) FROM sys_menu')).scalar_one() == 15
    title = await conn.exec_driver_sql("SELECT title FROM sys_menu WHERE name = 'PluginAppUpdate'")
    assert title.scalar_one() == 'app_update.menu'
    async with conn.begin_nested() as savepoint:
        await conn.exec_driver_sql("UPDATE sys_menu SET perms = 'host:permission' WHERE name = 'AppUpdateReleaseAdd'")
        with pytest.raises(Exception, match='app_update menu identity conflict'):
            await execute_statements(conn, init)
        await savepoint.rollback()


async def check_postgresql_seed_conflicts(conn: AsyncConnection, init: Sequence[str]) -> None:
    async with conn.begin_nested() as savepoint:
        await conn.exec_driver_sql("DELETE FROM sys_menu WHERE name = 'AppUpdateReleaseDel'")
        await conn.exec_driver_sql(
            f"INSERT INTO sys_menu (id, title, name) VALUES ({BASE_ID + 15}, 'host', 'HostMenu')"
        )
        with pytest.raises(Exception, match='app_update menu ID/name conflict'):
            await execute_statements(conn, init)
        await savepoint.rollback()
    async with conn.begin_nested() as savepoint:
        await conn.exec_driver_sql("DELETE FROM app_update_channel WHERE code = 'stable'")
        await conn.exec_driver_sql(
            'INSERT INTO app_update_channel (id, application_id, code, name) '
            f"VALUES ({BASE_ID + 102}, 42, 'host', 'host')"
        )
        with pytest.raises(Exception, match='app_update channel seed ID conflict'):
            await execute_statements(conn, init)
        await savepoint.rollback()


async def check_postgresql_uninstall(conn: AsyncConnection, destroy: Sequence[str]) -> None:
    await conn.exec_driver_sql('INSERT INTO sys_role_menu SELECT 1, id FROM sys_menu')
    await conn.exec_driver_sql("INSERT INTO sys_menu (id, title, name) VALUES (99, 'host', 'HostMenu')")
    # The host has no parent FK: the explicit guard must preserve menus and grants.
    for legacy in (False, True):
        async with conn.begin_nested() as fixture:
            if legacy:
                await conn.exec_driver_sql(
                    "UPDATE sys_menu SET perms = 'host:permission' WHERE name = 'AppUpdateReleaseAdd'"
                )
            else:
                await conn.exec_driver_sql("""INSERT INTO sys_menu (id, title, name, parent_id)
                    VALUES (100, 'custom child', 'ForeignChild', 77)""")
                await conn.exec_driver_sql('INSERT INTO sys_role_menu VALUES (2, 100)')
            menus = (await conn.exec_driver_sql('SELECT * FROM sys_menu ORDER BY id')).all()
            grants = (await conn.exec_driver_sql('SELECT * FROM sys_role_menu ORDER BY role_id, menu_id')).all()
            async with conn.begin_nested() as attempt:
                with pytest.raises(Exception, match='app_update external child menu conflict'):
                    await execute_statements(conn, destroy)
                await attempt.rollback()
            remaining_menus = await conn.exec_driver_sql('SELECT * FROM sys_menu ORDER BY id')
            remaining_grants = await conn.exec_driver_sql('SELECT * FROM sys_role_menu ORDER BY role_id, menu_id')
            assert remaining_menus.all() == menus
            assert remaining_grants.all() == grants
            assert (await conn.exec_driver_sql('SELECT count(*) FROM app_update_application')).scalar_one() == 1
            await fixture.rollback()
    for _ in range(2):
        await execute_statements(conn, destroy)
    assert (await conn.exec_driver_sql('SELECT name FROM sys_menu')).scalars().all() == ['HostMenu']
    assert (await conn.exec_driver_sql('SELECT count(*) FROM sys_role_menu')).scalar_one() == 0


@pytest.mark.anyio
@pytest.mark.parametrize(['mode'], [[''], ['_snowflake']])
async def test_postgresql_in_disposable_local_schema(mode: str) -> None:
    """Repeat, partial repair, legacy IDs, identity conflicts and guarded uninstall."""
    url = os.environ.get('APP_UPDATE_SQL_TEST_URL')
    if not url:
        pytest.skip('No explicit disposable local PostgreSQL test database supplied')
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlparse import split

    parsed = make_url(url)
    assert parsed.drivername == 'postgresql+asyncpg'
    assert parsed.host in ('localhost', '127.0.0.1', '::1')
    assert parsed.database == 'fba_app_update_sql_test'
    schema = f'app_update_sql_{uuid.uuid4().hex}'
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA {schema}')
            await conn.exec_driver_sql(f'SET search_path TO {schema}')
            schema_source = await anyio.Path(SQL / 'postgresql' / f'schema{mode}.sql').read_text(encoding='utf-8')
            await setup_postgresql_schema(conn, mode, split(schema_source))
            init = await parse_sql_script(str(SQL / 'postgresql' / f'init{mode}.sql'))
            await check_postgresql_repeat(conn, mode, init)
            await check_postgresql_partial_repair(conn, mode, init)
            await check_postgresql_identity_conflicts(conn, init)
            if mode:
                await check_postgresql_seed_conflicts(conn, init)
            destroy = await parse_sql_script(str(SQL / 'postgresql' / f'destroy{mode}.sql'), is_destroy=True)
            await check_postgresql_uninstall(conn, destroy)
            await conn.rollback()  # Includes private schema creation; nothing is committed.
    finally:
        await engine.dispose()
