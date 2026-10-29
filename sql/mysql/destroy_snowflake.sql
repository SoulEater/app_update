SET @app_update_destroy_menu_ids = (
    WITH plugin_menus AS (
        SELECT m.id FROM sys_menu m JOIN JSON_TABLE('[
            ["PluginAppUpdate",0,"/plugins/app-update",null,null],
            ["PluginAppUpdateReleases",1,"/plugins/app-update/releases","/plugins/app_update/views/releases",null],
            ["PluginAppUpdateApplications",1,"/plugins/app-update/applications","/plugins/app_update/views/applications",null],
            ["AppUpdateApplicationAdd",2,null,null,"app_update:application:add"],
            ["AppUpdateApplicationEdit",2,null,null,"app_update:application:edit"],
            ["AppUpdateApplicationDel",2,null,null,"app_update:application:del"],
            ["AppUpdateChannelAdd",2,null,null,"app_update:channel:add"],
            ["AppUpdateChannelEdit",2,null,null,"app_update:channel:edit"],
            ["AppUpdateChannelDel",2,null,null,"app_update:channel:del"],
            ["AppUpdateReleaseAdd",2,null,null,"app_update:release:add"],
            ["AppUpdateReleaseEdit",2,null,null,"app_update:release:edit"],
            ["AppUpdateReleaseUpload",2,null,null,"app_update:release:upload"],
            ["AppUpdateReleasePublish",2,null,null,"app_update:release:publish"],
            ["AppUpdateReleasePause",2,null,null,"app_update:release:pause"],
            ["AppUpdateReleaseDel",2,null,null,"app_update:release:del"]
        ]', '$[*]' COLUMNS (
            name VARCHAR(64) PATH '$[0]', type INT PATH '$[1]', path VARCHAR(200) PATH '$[2]',
            component VARCHAR(256) PATH '$[3]', perms VARCHAR(128) PATH '$[4]'
        )) s ON m.name = s.name AND m.type = s.type AND m.path <=> s.path
            AND m.component <=> s.component AND m.perms <=> s.perms
    )
    -- A second scalar row raises error 1242 before any deletion, even without a parent FK.
    SELECT JSON_ARRAYAGG(id) FROM plugin_menus
    UNION ALL SELECT JSON_ARRAY() WHERE EXISTS (
        SELECT 1 FROM sys_menu child
        JOIN plugin_menus parent ON child.parent_id = parent.id
        LEFT JOIN plugin_menus own ON child.id = own.id
        WHERE own.id IS NULL
    )
);

DELETE FROM sys_role_menu WHERE menu_id IN (
    SELECT id FROM JSON_TABLE(coalesce(@app_update_destroy_menu_ids, JSON_ARRAY()), '$[*]'
        COLUMNS (id BIGINT PATH '$')) menus
);
DELETE FROM sys_menu WHERE type = 2 AND id IN (
    SELECT id FROM JSON_TABLE(coalesce(@app_update_destroy_menu_ids, JSON_ARRAY()), '$[*]'
        COLUMNS (id BIGINT PATH '$')) menus
);
DELETE FROM sys_menu WHERE type = 1 AND id IN (
    SELECT id FROM JSON_TABLE(coalesce(@app_update_destroy_menu_ids, JSON_ARRAY()), '$[*]'
        COLUMNS (id BIGINT PATH '$')) menus
);
DELETE FROM sys_menu WHERE type = 0 AND id IN (
    SELECT id FROM JSON_TABLE(coalesce(@app_update_destroy_menu_ids, JSON_ARRAY()), '$[*]'
        COLUMNS (id BIGINT PATH '$')) menus
);

DROP TABLE IF EXISTS app_update_artifact;
DROP TABLE IF EXISTS app_update_release;
DROP TABLE IF EXISTS app_update_channel;
DROP TABLE IF EXISTS app_update_application;
