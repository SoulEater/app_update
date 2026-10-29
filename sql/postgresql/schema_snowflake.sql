-- Manual deployment only: create schema before running init_snowflake.sql. CLI uses ORM metadata.
create table if not exists app_update_application (
    id bigint not null primary key,
    key varchar(64) not null,
    name varchar(128) not null,
    description text default null,
    status varchar(16) default 'enabled',
    deleted bigint default 0,
    deleted_time timestamptz default null,
    created_time timestamptz default null,
    updated_time timestamptz default null,
    unique (key)
);
comment on table app_update_application is '应用更新-应用表';
comment on column app_update_application.key is '应用标识';
create table if not exists app_update_channel (
    id bigint not null primary key,
    application_id bigint not null references app_update_application (id),
    code varchar(32) not null,
    name varchar(64) not null,
    status varchar(16) default 'enabled',
    current_release_id bigint default null,
    deleted bigint default 0,
    deleted_time timestamptz default null,
    created_time timestamptz default null,
    updated_time timestamptz default null,
    constraint uk_app_update_channel_app_code unique (application_id, code)
);
create index if not exists ix_app_update_channel_application_id on app_update_channel (application_id);
create index if not exists ix_app_update_channel_current_release_id on app_update_channel (current_release_id);
comment on table app_update_channel is '应用更新-渠道表';
comment on column app_update_channel.current_release_id is '客户端当前可见版本ID，逻辑关联 app_update_release.id';
create table if not exists app_update_release (
    id bigint not null primary key,
    application_id bigint not null references app_update_application (id),
    channel_id bigint not null references app_update_channel (id),
    version varchar(32) not null,
    platform varchar(16) default 'win32',
    arch varchar(16) default 'x64',
    release_notes text default null,
    status varchar(16) default 'draft',
    signature_status varchar(32) default null,
    published_by bigint default null,
    published_at timestamptz default null,
    deleted bigint default 0,
    deleted_time timestamptz default null,
    created_time timestamptz default null,
    updated_time timestamptz default null,
    constraint uk_app_update_release_identity unique (application_id, channel_id, version, platform, arch)
);
create index if not exists ix_app_update_release_application_id on app_update_release (application_id);
create index if not exists ix_app_update_release_channel_id on app_update_release (channel_id);
create index if not exists ix_app_update_release_published_by on app_update_release (published_by);
comment on table app_update_release is '应用更新-版本表';
comment on column app_update_release.published_by is '发布人 sys_user.id，逻辑关联';
create table if not exists app_update_artifact (
    id bigint not null primary key,
    release_id bigint not null references app_update_release (id),
    kind varchar(16) not null,
    filename varchar(255) not null,
    storage_path varchar(512) not null,
    size bigint not null,
    sha256 varchar(64) not null,
    sha512 varchar(128) default null,
    deleted bigint default 0,
    deleted_time timestamptz default null,
    created_time timestamptz default null,
    updated_time timestamptz default null,
    constraint uk_app_update_artifact_release_kind unique (release_id, kind)
);
create index if not exists ix_app_update_artifact_release_id on app_update_artifact (release_id);
comment on table app_update_artifact is '应用更新-产物表';
