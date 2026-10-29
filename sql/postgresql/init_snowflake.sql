DO $app_update$
DECLARE
    seed record;
    existing sys_menu%ROWTYPE;
    parent bigint;
    demo_id bigint;
BEGIN
    -- Reserved bootstrap namespace: 880210000000001..103 (not runtime snowflake IDs).
    -- Existing names retain their IDs only if their route/permission and parent identify this plugin.
    FOR seed IN SELECT * FROM (VALUES
        (880210000000001::bigint, 'app_update.menu', 'PluginAppUpdate', '/plugins/app-update', 21, 'ant-design:cloud-sync-outlined', 0, NULL, NULL, NULL),
        (880210000000002, 'app_update.releases.menu', 'PluginAppUpdateReleases', '/plugins/app-update/releases', 1, 'ant-design:rocket-outlined', 1, '/plugins/app_update/views/releases', NULL, 'PluginAppUpdate'),
        (880210000000003, 'app_update.applications.menu', 'PluginAppUpdateApplications', '/plugins/app-update/applications', 2, 'ant-design:appstore-outlined', 1, '/plugins/app_update/views/applications', NULL, 'PluginAppUpdate'),
        (880210000000004, '新增应用', 'AppUpdateApplicationAdd', NULL, 1, NULL, 2, NULL, 'app_update:application:add', 'PluginAppUpdateApplications'),
        (880210000000005, '修改应用', 'AppUpdateApplicationEdit', NULL, 2, NULL, 2, NULL, 'app_update:application:edit', 'PluginAppUpdateApplications'),
        (880210000000006, '删除应用', 'AppUpdateApplicationDel', NULL, 3, NULL, 2, NULL, 'app_update:application:del', 'PluginAppUpdateApplications'),
        (880210000000007, '新增渠道', 'AppUpdateChannelAdd', NULL, 4, NULL, 2, NULL, 'app_update:channel:add', 'PluginAppUpdateApplications'),
        (880210000000008, '修改渠道', 'AppUpdateChannelEdit', NULL, 5, NULL, 2, NULL, 'app_update:channel:edit', 'PluginAppUpdateApplications'),
        (880210000000009, '删除渠道', 'AppUpdateChannelDel', NULL, 6, NULL, 2, NULL, 'app_update:channel:del', 'PluginAppUpdateApplications'),
        (880210000000010, '新增版本', 'AppUpdateReleaseAdd', NULL, 1, NULL, 2, NULL, 'app_update:release:add', 'PluginAppUpdateReleases'),
        (880210000000011, '修改版本', 'AppUpdateReleaseEdit', NULL, 2, NULL, 2, NULL, 'app_update:release:edit', 'PluginAppUpdateReleases'),
        (880210000000012, '上传产物', 'AppUpdateReleaseUpload', NULL, 3, NULL, 2, NULL, 'app_update:release:upload', 'PluginAppUpdateReleases'),
        (880210000000013, '发布版本', 'AppUpdateReleasePublish', NULL, 4, NULL, 2, NULL, 'app_update:release:publish', 'PluginAppUpdateReleases'),
        (880210000000014, '暂停版本', 'AppUpdateReleasePause', NULL, 5, NULL, 2, NULL, 'app_update:release:pause', 'PluginAppUpdateReleases'),
        (880210000000015, '删除版本', 'AppUpdateReleaseDel', NULL, 6, NULL, 2, NULL, 'app_update:release:del', 'PluginAppUpdateReleases')
    ) AS s(id, title, name, path, sort, icon, type, component, perms, parent_name)
    ORDER BY id
    LOOP
        IF EXISTS (SELECT 1 FROM sys_menu WHERE id = seed.id AND name <> seed.name)
           OR (SELECT count(*) FROM sys_menu WHERE name = seed.name) > 1 THEN
            RAISE EXCEPTION 'app_update menu ID/name conflict: %', seed.name;
        END IF;
        parent := NULL;
        IF seed.parent_name IS NOT NULL THEN
            SELECT id INTO STRICT parent FROM sys_menu WHERE name = seed.parent_name;
        END IF;
        SELECT * INTO existing FROM sys_menu WHERE name = seed.name;
        IF FOUND THEN
            IF existing.type IS DISTINCT FROM seed.type
               OR existing.path IS DISTINCT FROM seed.path
               OR existing.component IS DISTINCT FROM seed.component
               OR existing.perms IS DISTINCT FROM seed.perms
               OR existing.parent_id IS DISTINCT FROM parent
               OR existing.deleted <> 0 THEN
                RAISE EXCEPTION 'app_update menu identity conflict: %', seed.name;
            END IF;
            UPDATE sys_menu SET title = seed.title WHERE id = existing.id;
        ELSE
            INSERT INTO sys_menu (id, title, name, path, sort, icon, type, component, perms, status, display, cache, link, remark, parent_id, deleted, created_time, updated_time)
            VALUES (seed.id, seed.title, seed.name, seed.path, seed.sort, seed.icon, seed.type, seed.component, seed.perms, 1, CASE WHEN seed.type = 2 THEN 0 ELSE 1 END, 1, '', NULL, parent, 0, now(), NULL);
        END IF;
    END LOOP;
    IF EXISTS (SELECT 1 FROM app_update_application WHERE id = 880210000000101 AND key <> 'demo') THEN
        RAISE EXCEPTION 'app_update demo seed ID conflict';
    END IF;
    INSERT INTO app_update_application (id, key, name, description, status, deleted, created_time)
    SELECT 880210000000101, 'demo', 'Demo', NULL, 'enabled', 0, now()
    WHERE NOT EXISTS (SELECT 1 FROM app_update_application WHERE key = 'demo');
    SELECT id INTO STRICT demo_id FROM app_update_application WHERE key = 'demo' AND deleted = 0;
    IF EXISTS (SELECT 1 FROM app_update_channel WHERE id = 880210000000102 AND (application_id <> demo_id OR code <> 'stable'))
       OR EXISTS (SELECT 1 FROM app_update_channel WHERE id = 880210000000103 AND (application_id <> demo_id OR code <> 'beta')) THEN
        RAISE EXCEPTION 'app_update channel seed ID conflict';
    END IF;
    INSERT INTO app_update_channel (id, application_id, code, name, status, deleted, created_time)
    SELECT 880210000000102, demo_id, 'stable', '正式版', 'enabled', 0, now()
    WHERE NOT EXISTS (SELECT 1 FROM app_update_channel WHERE application_id = demo_id AND code = 'stable');
    INSERT INTO app_update_channel (id, application_id, code, name, status, deleted, created_time)
    SELECT 880210000000103, demo_id, 'beta', '测试版', 'enabled', 0, now()
    WHERE NOT EXISTS (SELECT 1 FROM app_update_channel WHERE application_id = demo_id AND code = 'beta');
END;
$app_update$;
