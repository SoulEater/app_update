SET @app_update_menus = '[
[880210000000001,"app_update.menu","PluginAppUpdate","/plugins/app-update",21,"ant-design:cloud-sync-outlined",0,null,null,null],
[880210000000002,"app_update.releases.menu","PluginAppUpdateReleases","/plugins/app-update/releases",1,"ant-design:rocket-outlined",1,"/plugins/app_update/views/releases",null,"PluginAppUpdate"],
[880210000000003,"app_update.applications.menu","PluginAppUpdateApplications","/plugins/app-update/applications",2,"ant-design:appstore-outlined",1,"/plugins/app_update/views/applications",null,"PluginAppUpdate"],
[880210000000004,"新增应用","AppUpdateApplicationAdd",null,1,null,2,null,"app_update:application:add","PluginAppUpdateApplications"],
[880210000000005,"修改应用","AppUpdateApplicationEdit",null,2,null,2,null,"app_update:application:edit","PluginAppUpdateApplications"],
[880210000000006,"删除应用","AppUpdateApplicationDel",null,3,null,2,null,"app_update:application:del","PluginAppUpdateApplications"],
[880210000000007,"新增渠道","AppUpdateChannelAdd",null,4,null,2,null,"app_update:channel:add","PluginAppUpdateApplications"],
[880210000000008,"修改渠道","AppUpdateChannelEdit",null,5,null,2,null,"app_update:channel:edit","PluginAppUpdateApplications"],
[880210000000009,"删除渠道","AppUpdateChannelDel",null,6,null,2,null,"app_update:channel:del","PluginAppUpdateApplications"],
[880210000000010,"新增版本","AppUpdateReleaseAdd",null,1,null,2,null,"app_update:release:add","PluginAppUpdateReleases"],
[880210000000011,"修改版本","AppUpdateReleaseEdit",null,2,null,2,null,"app_update:release:edit","PluginAppUpdateReleases"],
[880210000000012,"上传产物","AppUpdateReleaseUpload",null,3,null,2,null,"app_update:release:upload","PluginAppUpdateReleases"],
[880210000000013,"发布版本","AppUpdateReleasePublish",null,4,null,2,null,"app_update:release:publish","PluginAppUpdateReleases"],
[880210000000014,"暂停版本","AppUpdateReleasePause",null,5,null,2,null,"app_update:release:pause","PluginAppUpdateReleases"],
[880210000000015,"删除版本","AppUpdateReleaseDel",null,6,null,2,null,"app_update:release:del","PluginAppUpdateReleases"]
]';

SET @app_update_menu_identity_conflict = (
    -- Error 1242 aborts on duplicate names, foreign identities and existing orphans.
    -- Reserved snowflake bootstrap IDs 880210000000001..103 are below 2^53.
    SELECT 1 UNION ALL SELECT 2 WHERE EXISTS (
        SELECT 1 FROM JSON_TABLE(@app_update_menus, '$[*]' COLUMNS (
            id BIGINT PATH '$[0]', name VARCHAR(64) PATH '$[2]', path VARCHAR(200) PATH '$[3]', type INT PATH '$[6]',
            component VARCHAR(256) PATH '$[7]', perms VARCHAR(128) PATH '$[8]', parent_name VARCHAR(64) PATH '$[9]'
        )) s
        LEFT JOIN sys_menu m ON m.name = s.name
        LEFT JOIN sys_menu occupied ON occupied.id = s.id
        LEFT JOIN sys_menu p ON p.name = s.parent_name
        WHERE (occupied.id IS NOT NULL AND occupied.name <> s.name)
           OR (SELECT count(*) FROM sys_menu duplicates WHERE duplicates.name = s.name) > 1
           OR (m.id IS NOT NULL AND (
               NOT (m.type <=> s.type) OR NOT (m.path <=> s.path)
               OR NOT (m.component <=> s.component) OR NOT (m.perms <=> s.perms)
               OR NOT (m.parent_id <=> p.id) OR m.deleted <> 0
               OR (s.parent_name IS NOT NULL AND p.id IS NULL)
           ))
    )
);

SET @app_update_demo_seed_conflict = (
    SELECT 1 UNION ALL SELECT 2 WHERE EXISTS (
        SELECT 1 FROM app_update_application WHERE id = 880210000000101 AND `key` <> 'demo'
    ) OR EXISTS (SELECT 1 FROM app_update_application WHERE `key` = 'demo' AND deleted <> 0)
);

SET @app_update_demo_id = (SELECT id FROM app_update_application WHERE `key` = 'demo');

SET @app_update_channel_seed_conflict = (
    SELECT 1 UNION ALL SELECT 2 WHERE EXISTS (
        SELECT 1 FROM app_update_channel
        WHERE (id = 880210000000102 AND (NOT (application_id <=> @app_update_demo_id) OR code <> 'stable'))
           OR (id = 880210000000103 AND (NOT (application_id <=> @app_update_demo_id) OR code <> 'beta'))
    )
);

INSERT INTO sys_menu (id, title, name, path, sort, icon, type, component, perms, status, display, cache, link, remark, parent_id, deleted, created_time, updated_time)
SELECT s.id, s.title, s.name, s.path, s.sort, s.icon, s.type, s.component, s.perms, 1, 1, 1, '', NULL, NULL, 0, now(), NULL
FROM JSON_TABLE(@app_update_menus, '$[*]' COLUMNS (
    id BIGINT PATH '$[0]', title VARCHAR(64) PATH '$[1]', name VARCHAR(64) PATH '$[2]', path VARCHAR(200) PATH '$[3]',
    sort INT PATH '$[4]', icon VARCHAR(128) PATH '$[5]', type INT PATH '$[6]',
    component VARCHAR(256) PATH '$[7]', perms VARCHAR(128) PATH '$[8]'
)) s WHERE s.type = 0 AND NOT EXISTS (SELECT 1 FROM sys_menu m WHERE m.name = s.name);

INSERT INTO sys_menu (id, title, name, path, sort, icon, type, component, perms, status, display, cache, link, remark, parent_id, deleted, created_time, updated_time)
SELECT s.id, s.title, s.name, s.path, s.sort, s.icon, s.type, s.component, s.perms, 1, 1, 1, '', NULL, p.id, 0, now(), NULL
FROM JSON_TABLE(@app_update_menus, '$[*]' COLUMNS (
    id BIGINT PATH '$[0]', title VARCHAR(64) PATH '$[1]', name VARCHAR(64) PATH '$[2]', path VARCHAR(200) PATH '$[3]',
    sort INT PATH '$[4]', icon VARCHAR(128) PATH '$[5]', type INT PATH '$[6]',
    component VARCHAR(256) PATH '$[7]', perms VARCHAR(128) PATH '$[8]', parent_name VARCHAR(64) PATH '$[9]'
)) s JOIN sys_menu p ON p.name = s.parent_name
WHERE s.type = 1 AND NOT EXISTS (SELECT 1 FROM sys_menu m WHERE m.name = s.name);

INSERT INTO sys_menu (id, title, name, path, sort, icon, type, component, perms, status, display, cache, link, remark, parent_id, deleted, created_time, updated_time)
SELECT s.id, s.title, s.name, s.path, s.sort, s.icon, s.type, s.component, s.perms, 1, 0, 1, '', NULL, p.id, 0, now(), NULL
FROM JSON_TABLE(@app_update_menus, '$[*]' COLUMNS (
    id BIGINT PATH '$[0]', title VARCHAR(64) PATH '$[1]', name VARCHAR(64) PATH '$[2]', path VARCHAR(200) PATH '$[3]',
    sort INT PATH '$[4]', icon VARCHAR(128) PATH '$[5]', type INT PATH '$[6]',
    component VARCHAR(256) PATH '$[7]', perms VARCHAR(128) PATH '$[8]', parent_name VARCHAR(64) PATH '$[9]'
)) s JOIN sys_menu p ON p.name = s.parent_name
WHERE s.type = 2 AND NOT EXISTS (SELECT 1 FROM sys_menu m WHERE m.name = s.name);

INSERT INTO sys_menu (id, title, name, path, sort, icon, type, component, perms, status, display, cache, link, remark, parent_id, deleted, created_time, updated_time)
SELECT m.id, s.title, m.name, m.path, m.sort, m.icon, m.type, m.component, m.perms,
       m.status, m.display, m.cache, m.link, m.remark, m.parent_id, m.deleted, m.created_time, m.updated_time
FROM JSON_TABLE(@app_update_menus, '$[*]' COLUMNS (title VARCHAR(64) PATH '$[1]', name VARCHAR(64) PATH '$[2]')) s
JOIN sys_menu m ON m.name = s.name
ON DUPLICATE KEY UPDATE title = VALUES(title);

INSERT INTO app_update_application (id, `key`, name, description, status, deleted, created_time)
SELECT 880210000000101, 'demo', 'Demo', NULL, 'enabled', 0, now() FROM dual
WHERE NOT EXISTS (SELECT 1 FROM app_update_application WHERE `key` = 'demo');

INSERT INTO app_update_channel (id, application_id, code, name, status, deleted, created_time)
SELECT 880210000000102, a.id, 'stable', '正式版', 'enabled', 0, now()
FROM app_update_application a WHERE a.`key` = 'demo'
AND NOT EXISTS (SELECT 1 FROM app_update_channel c WHERE c.application_id = a.id AND c.code = 'stable');

INSERT INTO app_update_channel (id, application_id, code, name, status, deleted, created_time)
SELECT 880210000000103, a.id, 'beta', '测试版', 'enabled', 0, now()
FROM app_update_application a WHERE a.`key` = 'demo'
AND NOT EXISTS (SELECT 1 FROM app_update_channel c WHERE c.application_id = a.id AND c.code = 'beta');
