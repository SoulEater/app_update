DO $$
DECLARE
    menu_ids bigint[];
BEGIN
    SELECT coalesce(array_agg(m.id), ARRAY[]::bigint[]) INTO menu_ids
    FROM sys_menu m JOIN (VALUES
        ('PluginAppUpdate', 0, '/plugins/app-update', NULL, NULL),
        ('PluginAppUpdateReleases', 1, '/plugins/app-update/releases', '/plugins/app_update/views/releases', NULL),
        ('PluginAppUpdateApplications', 1, '/plugins/app-update/applications', '/plugins/app_update/views/applications', NULL),
        ('AppUpdateApplicationAdd', 2, NULL, NULL, 'app_update:application:add'),
        ('AppUpdateApplicationEdit', 2, NULL, NULL, 'app_update:application:edit'),
        ('AppUpdateApplicationDel', 2, NULL, NULL, 'app_update:application:del'),
        ('AppUpdateChannelAdd', 2, NULL, NULL, 'app_update:channel:add'),
        ('AppUpdateChannelEdit', 2, NULL, NULL, 'app_update:channel:edit'),
        ('AppUpdateChannelDel', 2, NULL, NULL, 'app_update:channel:del'),
        ('AppUpdateReleaseAdd', 2, NULL, NULL, 'app_update:release:add'),
        ('AppUpdateReleaseEdit', 2, NULL, NULL, 'app_update:release:edit'),
        ('AppUpdateReleaseUpload', 2, NULL, NULL, 'app_update:release:upload'),
        ('AppUpdateReleasePublish', 2, NULL, NULL, 'app_update:release:publish'),
        ('AppUpdateReleasePause', 2, NULL, NULL, 'app_update:release:pause'),
        ('AppUpdateReleaseDel', 2, NULL, NULL, 'app_update:release:del')
    ) AS s(name, type, path, component, perms)
        ON ROW(m.name, m.type, m.path, m.component, m.perms)
            IS NOT DISTINCT FROM ROW(s.name, s.type, s.path, s.component, s.perms);

    IF EXISTS (
        SELECT 1 FROM sys_menu
        WHERE parent_id = ANY(menu_ids) AND NOT (id = ANY(menu_ids))
    ) THEN
        RAISE EXCEPTION 'app_update external child menu conflict';
    END IF;

    DELETE FROM sys_role_menu WHERE menu_id = ANY(menu_ids);
    DELETE FROM sys_menu WHERE id = ANY(menu_ids) AND type = 2;
    DELETE FROM sys_menu WHERE id = ANY(menu_ids) AND type = 1;
    DELETE FROM sys_menu WHERE id = ANY(menu_ids) AND type = 0;
END $$;

DROP TABLE IF EXISTS app_update_artifact;
DROP TABLE IF EXISTS app_update_release;
DROP TABLE IF EXISTS app_update_channel;
DROP TABLE IF EXISTS app_update_application;
