# SQL deployment contract

- The standard FBA CLI creates tables through ORM metadata. `init.sql` and
  `init_snowflake.sql` contain only bootstrap data operations accepted by the
  official `backend.utils.sql_parser.parse_sql_script`.
- Manual deployments: first execute the matching `schema.sql` or
  `schema_snowflake.sql` using the database client, then execute the matching
  initializer. Schema scripts retain the previous table DDL and are **not** CLI
  initialization scripts. They do not migrate already-existing tables.
- MySQL requires **8.0.21+** (`JSON_TABLE` with JSON null support). PostgreSQL uses
  a transactional `DO` block. Run installation/uninstallation with exclusive
  maintenance access, inside a transaction, as the CLI does. Do not run the
  installer concurrently with menu administration or another installation.

## Reserved bootstrap IDs

**Only snowflake mode** reserves the following signed BIGINT values, all below
JavaScript's exact-integer limit (`2^53`). These are deterministic bootstrap IDs,
not generated runtime snowflakes. Autoincrement initialization omits seed IDs
entirely: the database allocates menu/application/channel primary keys normally.
MySQL's title synchronization reuses existing IDs only; it never allocates a
fixed bootstrap ID in autoincrement mode.

| Range / ID | Purpose |
| --- | --- |
| 880210000000001–880210000000015 | 3 menus and 12 permission buttons |
| 880210000000101 | Default `demo` application |
| 880210000000102 | Default `stable` channel |
| 880210000000103 | Default `beta` channel |

An existing `demo` application keeps its actual ID; its channels always resolve
that application by key. Existing plugin menus keep their IDs and role grants
when their name, route/component/permission, type and parent identity match.
Titles are synchronized. Missing menus/buttons are restored individually.
MySQL inserts root, pages and buttons in three layers; both dialects resolve
parents by actual menu name, never by an as-yet uninserted reserved parent ID.
A partial installation with missing descendants can be repaired. Existing
orphans or incompatible parent IDs are rejected rather than silently attached
to a different parent. PostgreSQL rejects such a mismatch transactionally;
MySQL checks it before allocating any menu rows.
A duplicate name, unrelated reserved-ID occupant, mismatching menu identity, or
conflicting seed ID fails rather than replacing somebody else's data. MySQL
reports scalar-subquery error **1242** from the named `*_conflict` guard;
PostgreSQL reports an explicit `app_update ... conflict` exception. Investigate
and resolve the conflict manually; do not bypass these guards with REPLACE,
INSERT IGNORE, or unconditional upserts. Soft-deleted demo applications must be
resolved manually rather than being silently resurrected.

No initializer/destroyer reseeds the shared `sys_menu` sequence. Autoincrement
mode uses ordinary sequence/AUTO_INCREMENT allocation and never advances it to
the reserved snowflake namespace. Run the script matching the host primary-key
mode; snowflake scripts are for non-autoincrement tables only. The reserved
range must not be allocated manually to other plugins. Snowflake bootstrap never
invokes `setval` or random SQL ID functions.

Destroy scripts first collect plugin menu IDs using a single exact, null-safe
`name/type/path/component/perms` identity whitelist. Before any deletion they
explicitly reject a child whose parent is in that set but whose own ID is not.
This does not depend on a `sys_menu.parent_id` foreign key (the host has none).
Custom children and incompatible legacy plugin identities are both external:
uninstallation stops without deleting their menus or role grants. PostgreSQL
raises `app_update external child menu conflict`; MySQL's first `SET` raises
scalar-subquery error **1242** by returning a second row. Investigate and resolve
the references manually; do not bypass the guard or delete host custom data.

After the guard passes, scripts delete matching plugin role-menu associations,
then buttons, child menus and the root menu, and finally the four plugin tables
in foreign-key dependency order. They neither disable constraints nor use
CASCADE. Other enforced foreign-key references can still reject uninstallation;
roll back on any error. Exclusive maintenance access remains required so menus
cannot change between the guard and deletion.

## Validation

From the host repository root, run in PowerShell using the project's Python:

```powershell
python -m pytest backend/plugin/app_update/tests/test_plugin_sql.py -q
```

The default tests call the current official parser on all eight release scripts
and check menu IDs/relationships, equivalent variants, retained manual DDL and
that the external-child guard precedes deletion.
They never connect to a database. Optional PostgreSQL execution tests require an
explicit `APP_UPDATE_SQL_TEST_URL` using `postgresql+asyncpg`, a loopback host and
the disposable database name `fba_app_update_sql_test`. They create a random
private schema inside a transaction and roll everything back; they do not use
host `.env`, application settings, Redis, or a default database URL. The fixture
has no menu-parent FK and verifies custom children (with role grants) and
incompatible legacy children block deletion without losing menus or grants;
after savepoint rollback, uninstallation succeeds twice. Do not set
this variable to any real application database. MySQL server execution remains
a separate disposable-database release verification step.
