# App Update

面向 FBA 的多应用、多渠道桌面更新插件。目标版本 **0.2.0**，配套前端为 **app_update_ui 0.2.0**；前后端均以 MIT 许可提供。授权及上游声明见 [LICENSE](LICENSE) 和 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

管理接口使用 JWT + RBAC；公开 feed 兼容 `electron-updater` generic provider。当前产物契约仅覆盖 **Windows x64 / NSIS**：版本号严格为 `x.y.z`，不支持预发布或构建后缀。

> 已在官方 FBA 1.16.0 + PostgreSQL 17.4／自增主键的隔离主站验证安装、管理 API 和动态 feed；详情见 [验收记录](docs/VALIDATION_2026-10-28.md)。这不等于四组合、完整卸载或真实 Windows 客户端验收通过。发布前按 [干净主站验收清单](docs/CLEAN_HOST_VALIDATION.md) 补齐其余结果。

## 架构与边界

```text
管理浏览器 → /api/v1/app-updates/* → 数据库元数据 + 共享产物目录
桌面客户端 → /updates/{application_key}/{channel_code}/latest.yml → 后端动态生成
桌面客户端 → /updates/{application_key}/{channel_code}/*.exe(.blockmap) → Nginx 静态下载
```

- 应用、渠道、版本和产物独立管理；版本状态为 `draft → published → paused`。
- 流式接收安装包、blockmap 和 manifest，服务端重新计算摘要并核对；校验通过后再切换渠道当前版本。
- 暂停当前版本时回退到符合条件的更低已发布版本，无可用版本则 feed 返回 404。
- 公开产物不受管理端 JWT 保护，不是私有文件库。暂停与停用只影响 feed，不撤销已知 URL、缓存或已下载文件。详见 [SECURITY.md](SECURITY.md)。

## 安装前准备

1. 准备已安装并初始化好的 FBA 主站、数据库（MySQL 8.0.21+ 或 PostgreSQL）和 Redis，确认数据库类型与主键模式。插件与离线生成器需要 Python 3.10+；实际版本仍以所选宿主的要求为准。
2. 备份数据库、产物目录及部署配置；在开发环境验证安装，再将已审查的提交部署到服务器。
3. 确认宿主具备当前插件安装器的 ORM 建表及 `parse_sql_script` 执行路径；不同宿主版本须自行验收。公开 feed 限流优先复用 FBA 1.16 的 `backend.common.limiter`，旧宿主回退到已有 `backend.utils.limiter`；两者均不可用或依赖损坏时明确失败，绝不静默关闭限流。`requirements.txt` 显式声明 YAML 序列化依赖，不依赖宿主的间接安装。
4. 源码仓库：[后端 app_update](https://github.com/SoulEater/app_update) 与[配套前端 app_update_ui](https://github.com/SoulEater/app_update_ui)。建议固定审查后的提交，不把主分支最新头等同于已验证版本。

**不要为了安装插件在现有数据库上执行 `fba init`。该命令会 `drop_all` 后重建宿主表。**

## 安装路径

### 方式一：FBA CLI（开发环境）

从已配置好宿主环境的后端主仓库根目录执行，以下两种后端安装方式二选一：

```bash
fba add --repo-url 'https://github.com/SoulEater/app_update.git'
# 或：本地后端 ZIP
fba add --path /absolute/path/app_update.zip
```

后端 ZIP 文件必须命名为 **`app_update.zip`**，且只含单一顶层目录 `app_update/`，其下直接包含 `plugin.toml`、`__init__.py` 等插件文件；不要直接使用顶层名为 `app_update-main/` 的源码归档。

CLI 先导入插件模型并通过 ORM `create_all` 创建缺失表，再执行与宿主数据库/主键模式匹配的标准 `init[_snowflake].sql`。标准 init 是菜单、权限、默认应用/渠道的初始化，不承担建表；标准 destroy 用于卸载。两者遵循官方 `parse_sql_script` 格式；PostgreSQL 的 `DO` 块可由解析器执行，不需要客户端 `DELIMITER` 等特殊命令。MySQL 最低要求 8.0.21，以支持当前种子脚本的 `JSON_TABLE` 空值处理。

`--db-type` / `--pk-type` 必须与宿主实际配置一致，默认取宿主值，不可只通过参数伪装另一种数据库。`--no-sql` 仅跳过 seed，仍需另行执行匹配的 init。具体可用参数以宿主 `fba add --help` 为准。

配套前端可用 CLI 安装并按提示选择前端项目根目录：

```bash
fba add --frontend --repo-url 'https://github.com/SoulEater/app_update_ui.git'
```

前端插件挂载位置为 `apps/web-antdv-next/src/plugins/app_update`。安装后确认实际检出的前后端均为审查后的 0.2.0 提交；CLI 拉取仓库不等于自动锁定某个 release。

### 管理后台上传的边界

开发模式后台也可上传 `app_update.zip`，但当前官方页面只负责解压、依赖、追加环境模板和登记变更；不像 CLI 那样完整执行插件初始化。出现“插件状态存在变更”是待完成配置／重启提醒，不代表已完成建表和菜单 seed。

上传后先检查配置，并通过匹配的插件初始化路径补齐数据库（仅插件 schema/init，不运行全站 `fba init`），再重启后端、安装配套前端。重启成功后由宿主正常重建插件缓存并清除 changed 标记，不应手动删标记掩盖加载错误。页面卸载不执行 destroy SQL，完整移除须参照下文 CLI／手工卸载流程。

### 方式二：submodule / 手工安装

在各自主仓库根目录执行：

```bash
# 后端
git submodule add 'https://github.com/SoulEater/app_update.git' backend/plugin/app_update
# 前端
git submodule add 'https://github.com/SoulEater/app_update_ui.git' apps/web-antdv-next/src/plugins/app_update
```

也可直接复制插件目录到上述位置。手工放置/添加 submodule **不等于执行 CLI 安装**，不能假设启动时自动完成建表与 seed。选择与宿主一致的一行，通过数据库原生客户端**先执行 schema，再执行 init**（路径相对后端插件根目录）：

| 数据库 / 主键 | 第一步：建插件表 | 第二步：seed |
| --- | --- | --- |
| MySQL / 自增 | `sql/mysql/schema.sql` | `sql/mysql/init.sql` |
| MySQL / 雪花 | `sql/mysql/schema_snowflake.sql` | `sql/mysql/init_snowflake.sql` |
| PostgreSQL / 自增 | `sql/postgresql/schema.sql` | `sql/postgresql/init.sql` |
| PostgreSQL / 雪花 | `sql/postgresql/schema_snowflake.sql` | `sql/postgresql/init_snowflake.sql` |

宿主系统表必须已经存在。`schema*.sql` 是手工 DDL，不交给标准插件 SQL 解析器执行；若已由 ORM 建表，不必再次执行 schema。不要混用自增/雪花脚本。默认 seed 为 `demo` 应用及 `stable`、`beta` 渠道，重复 init 不应覆盖已有业务数据或恢复用户已修改的配置。

初始化后重启后端，在菜单/角色管理为目标角色分配「应用更新」页面和按钮权限；前端重新构建并检查菜单可访问。菜单存在不等于普通角色已获得权限。

## 配置

本插件使用独立 `config.py` 的 `AppUpdateSettings`，不要求修改宿主 `backend/core/conf.py`。优先级为 **进程环境变量 > 宿主 `.env` > 插件 `plugin.toml [settings]`**。六个字段均有类型校验，非法配置启动失败；配置改变后需重启所有后端进程。

插件默认值：

```toml
[settings]
APP_UPDATE_STORAGE_DIR = "static/upload/app_updates"
APP_UPDATE_MAX_INSTALLER_BYTES = 536870912
APP_UPDATE_MAX_BLOCKMAP_BYTES = 10485760
APP_UPDATE_MAX_MANIFEST_BYTES = 1048576
APP_UPDATE_UPLOAD_CHUNK_BYTES = 1048576
APP_UPDATE_PUBLIC_BASE_URL = "https://example.com/updates"
```

### 配置项说明

以下按 TOML 顺序说明用途：

- `APP_UPDATE_STORAGE_DIR`：保存上传中转和正式产物的根目录，相对路径以宿主 `backend/` 为基准。
- `APP_UPDATE_MAX_INSTALLER_BYTES`：限制单个安装包的上传字节数。
- `APP_UPDATE_MAX_BLOCKMAP_BYTES`：限制单个 blockmap 的上传字节数。
- `APP_UPDATE_MAX_MANIFEST_BYTES`：限制 manifest 上传及签名信息读取的字节数。
- `APP_UPDATE_UPLOAD_CHUNK_BYTES`：控制上传流每次读取的字节数。
- `APP_UPDATE_PUBLIC_BASE_URL`：生成后台展示/复制的公开更新源基地址。

本插件在雪花主键模式下将主键、关联 ID 和发布/暂停结果 ID 序列化为十进制字符串，自增模式保留整数；配套 UI 0.2.0 不把雪花字符串转成 JavaScript `number`，避免精度丢失。自定义调用方也应原样保存 ID。

大小和分块字段必须为正整数，拒绝布尔和浮点值；manifest 与分块字段最大 **16 MiB（16777216 字节）**，安装包和 blockmap 上限为正整数。存储目录不能是空白字符串或包含 NUL。URL 必须是有效 HTTP(S) 地址，不能含认证信息、query 或 fragment；生产环境使用 HTTPS。

例如在宿主 `.env` 中设置：

```dotenv
APP_UPDATE_STORAGE_DIR='static/upload/app_updates'
APP_UPDATE_PUBLIC_BASE_URL='https://downloads.example.com/updates'
```

示例域名须替换。存储路径变化时必须同步修改 Nginx 映射和共享卷，避免把整个上传目录公开。

## 构建与 manifest

应用 key 决定文件名：**仅将 key 的首字母大写，其余保持不变**。如 `myapp` 的 1.2.3 版本必须使用：

```text
Myapp-1.2.3-win-x64.exe
Myapp-1.2.3-win-x64.exe.blockmap
```

electron-builder 的默认命名**不保证**符合此契约；请显式配置 `artifactName`、NSIS target 与 x64，并核对生成的安装包及 blockmap。例如应用 key 为 `myapp` 时，可使用 `"win": { "target": [{ "target": "nsis", "arch": ["x64"] }], "artifactName": "Myapp-${version}-win-x64.${ext}" }`；随后以实际构建输出为准验证对应 `.blockmap`。不要只重命名安装包而忽略 blockmap/构建元数据。

在插件根目录生成 schemaVersion=2 manifest（脚本只需 Python 标准库）：

```bash
python scripts/generate_manifest.py \
  --application-key myapp --version 1.2.3 \
  --installer dist/Myapp-1.2.3-win-x64.exe \
  --blockmap dist/Myapp-1.2.3-win-x64.exe.blockmap \
  --output dist/release-manifest.json
```

可选 `--signature-file path/to/signature.json` 导入构建侧签名声明，`--force` 允许替换已存在的输出（不得覆盖输入文件）。未提供声明时 `signature.status` 为 **`unknown`**，脚本绝不根据摘要自动标记 `valid`。示例见 [examples/manifest/](examples/manifest/)。生成器不是签名工具，也不执行 Windows 系统验签。

## 发布和客户端接入

1. 新建应用及渠道（应用 key、渠道 code 创建后不可修改）。
2. 在「版本管理」创建严格 `x.y.z` 草稿，填写说明。
3. 上传安装包、blockmap、manifest 三个文件；服务端复算 SHA-256 / SHA-512 并比对身份、文件名、大小和摘要。
4. 发布版本后检查 `latest.yml`，再发布更高版本验证客户端更新。
5. 暂停当前版本验证回退；禁用应用或渠道验证 feed 404。已发布产物禁止重新上传或同名覆盖。

```js
const { autoUpdater } = require('electron-updater');
autoUpdater.setFeedURL({
  provider: 'generic',
  url: 'https://downloads.example.com/updates/myapp/stable/',
});
autoUpdater.checkForUpdatesAndNotify();
```

feed 无鉴权，按 IP 限流；应用/渠道停用、无当前已发布版本或产物缺失时返回 404。客户端是否允许降级是客户端策略，**feed 回退不保证已安装高版本自动降级**。

管理路由前缀 `/api/v1/app-updates`，包含 `/applications`、`/channels`、`/releases` 及 `/releases/{pk}/{artifacts,publish,pause}`。按钮权限为 `app_update:application:{add,edit,del}`、`app_update:channel:{add,edit,del}`、`app_update:release:{add,edit,upload,publish,pause,del}`。

版本列表/详情的 `signature_info` 为可空只读信息，白名单字段为 `publisher_name`、`installer_thumbprint`、`application_thumbprint`、`timestamp_subject`。只有 manifest 摘要和版本身份匹配时才读取；缺失、损坏或不合规时降级为 `null`，不修改原有 `signature_status`，不做历史回填。这些字段都是声明，**不是服务端验签结果**。

## Nginx 与服务器部署

使用 [examples/nginx/app_update.conf](examples/nginx/app_update.conf)，按 [Nginx 示例说明](examples/nginx/README.md) 替换后端 upstream、存储绝对路径和域名，并在 Nginx **server 级** include。仅白名单公开匹配契约的 `.exe`、`.exe.blockmap`；`latest.yml` 代理后端；其余 `/updates/` 请求返回 404。不要配置能暴露 manifest、`.staging` 或目录索引的宽泛 alias。

后端对产物目录可写、Nginx 只读共享同一目录。核对所有入口的请求体上限及上传超时，并验证 Range/206。开发环境可直接访问后端 feed，但完整安装包下载需要实际配置静态服务器，不应假设后端提供相同下载路由。

服务器只部署已审查的主仓库提交及其固定子模块 SHA，不现场编辑 Git 管理文件。例如在受控发布目录选择已批准的主仓库 SHA：

```bash
git fetch origin
git checkout --detach <approved-host-sha>
git submodule sync --recursive
git submodule update --init --recursive
git submodule status --recursive
```

`<approved-host-sha>` 必须替换为实际 SHA。**不要使用 `git submodule update --remote`**；主仓库先经过 MR 更新插件指针，服务器只复现该精确指针。按宿主流程构建/重启服务；若反向代理缓存了容器地址，确认后端重建后能重新解析。备份后执行必要 SQL，再运行验收。上传暂存与正式目录必须在同一支持硬链接的本地文件系统：插件使用原子 no-clobber 链接提交产物，已有文件即使遇到并发上传也不会被覆盖；不支持硬链接的文件系统会使上传失败，须更换为受支持的存储。

## 从 0.1 升级

备份数据库、产物和配置，更新前后端至审查后的 0.2.0 提交并重启/重建服务。本次对现有 0.1 数据库**无需结构迁移，也不回填历史签名信息**；不要通过销毁重建或 `fba init` 升级。核对原有环境变量是否通过新独立配置校验，并收紧 Nginx 下载规则。需要补充默认菜单/seed 时，仅执行匹配的 init，确认不覆盖已有数据。

## 测试与验收

从后端主仓库根目录运行：

```bash
pytest backend/plugin/app_update/tests/ -q
```

自动化测试覆盖版本比较、manifest、产物存储、签名信息、发布/feed 逻辑以及配置和生成器等；实际通过项以当前提交的 pytest 日志为准，不把跳过的集成测试计入通过。

```bash
# 仅在隔离的专用测试数据库和 Redis 环境中使用
FBA_INTEGRATION=1 pytest backend/plugin/app_update/tests/ -q
```

不可对生产库或既有业务库开启集成测试。干净主站的四组合安装、前端权限、真实 Nginx/Range 与客户端行为由用户按 [CLEAN_HOST_VALIDATION.md](docs/CLEAN_HOST_VALIDATION.md) 验收；仓库中的测试并不替代它们。

## 卸载

**卸载会破坏数据：先备份数据库、产物目录和配置，并通知客户端停止使用旧 feed。CLI 自动备份插件代码不能替代数据库和产物备份。**

- CLI 安装：开发环境执行 `fba remove app_update`，宿主按数据库/主键模式执行对应 destroy 并移除插件。若使用 `--no-sql` 保留数据，须记录遗留表和菜单并另行安排清理。
- submodule/手工安装：通过数据库原生客户端执行匹配的 `sql/{mysql,postgresql}/destroy.sql` 或 `destroy_snowflake.sql`，再删除目录；submodule 在开发主仓库执行 `git submodule deinit -f backend/plugin/app_update`、`git rm -f backend/plugin/app_update`，通过 MR 更新宿主指针/配置，不在只读服务器现场执行此开发操作。
- 移除前端插件、角色菜单引用和相关构建配置，重新构建前端；确认无其他应用共用目录后再清理产物。
- 移除 `APP_UPDATE_*` 环境变量与 `.env` 项、Nginx include/静态映射，重启后端与代理并验证旧 feed/下载入口不可用。CDN/客户端缓存需另行处理。

## 源码与维护

本项目按 MIT 许可提供。这是 0.2.0 源码首次公开导入，**不等于已创建版本标签、发布安装附件或完成全部兼容性验收**。公开仓库从已验证源码创建独立初始提交，不包含原开发仓库历史；运行代码与对应验证基线一致，公开副本只补充实际仓库地址和文档说明。

维护者：[SoulEater](https://github.com/SoulEater)。普通问题通过 [GitHub Issues](https://github.com/SoulEater/app_update/issues) 反馈；安全问题按 [SECURITY.md](SECURITY.md) 私下报告。后续提交仍须检查凭据、运行配置及附件；没有导入旧历史不代表可以跳过新提交的敏感信息检查。
