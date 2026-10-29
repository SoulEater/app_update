# 插件协作规范

适用于本插件仓库。宿主指集成本插件的 FBA 主仓库；后端 `app_update` 与前端 `app_update_ui` 是独立插件仓库。

## 修改边界

- 优先在插件内解决问题，遵循 API → schema → service → CRUD → model 分层及宿主编码规范。
- 不要求修改宿主 `backend/core/conf.py` 来声明插件配置，也不擅自修改宿主共享卷布局。
- 六个配置项在 `plugin.toml [settings]` 保留非空默认值，由插件独立 `config.py` 的 `AppUpdateSettings` 校验，优先级为环境变量 > 宿主 `.env` > TOML，变更后重启。新增字段须同时更新校验、测试和 README；配置项说明按 TOML 顺序只解释用途。
- 产物默认写入 `static/upload/app_updates`，通过共享目录交给 Nginx；公开路径遵循 `/updates/`，不要暴露 manifest、暂存文件或其他上传文件。
- 不在文档或示例中加入内部路径、生产域名、凭据或个人信息；未知仓库 owner 使用明确需替换的 `<owner>`，不要伪造可用地址。

## 数据库与兼容性

- 维护 MySQL/PostgreSQL × 自增/雪花四套行为。标准 `init[_snowflake].sql` 与 `destroy[_snowflake].sql` 必须兼容宿主官方 `parse_sql_script`。
- CLI 安装先 ORM 建表再 init；手工/submodule 安装先执行对应 `schema[_snowflake].sql` 再 init。手工 DDL 不混入标准 init。
- init 应可重复执行，默认 seed 不覆盖已有应用/渠道数据。结构迁移须单独提供幂等方案并明确备份要求。
- 0.1 → 0.2.0 不需要结构迁移或历史签名信息回填；签名信息只是只读构建声明，不代表服务器验签。
- 严禁为了装插件在现有库执行 `fba init`，它会 `drop_all`。`FBA_INTEGRATION=1` 仅用于隔离专用测试库及 Redis。
- 不将测试文件存在、单测通过或 SQL 静态解析通过写成真实四组合/干净主站验收通过。记录实际命令、版本、通过/跳过数以及未验收项，遵循 `docs/CLEAN_HOST_VALIDATION.md`。

## 分支与提交流程

1. 在插件仓库从主分支新建 `feat/*` 或 `fix/*`；后端与前端配套修改分别审查。
2. 向插件主分支提交 MR/PR，合并后再在宿主主仓库提交独立的子模块指针 bump，例如 `chore: bump app_update submodule (release readiness)`。
3. 宿主 MR/PR 标明精确插件 SHA、配套前端版本、配置变化、SQL 是否必要、备份及回滚步骤。
4. 未经用户授权不 commit、push、创建公开仓库、发布 release 或部署。禁止擅自改写已有私有历史或 force-push；公开前检查完整历史中的域名、邮箱与敏感资料并确认处理策略。

## 只读服务器部署

- 服务器不编辑 Git 管理文件；只部署已批准的宿主 SHA 和该提交锁定的插件 SHA。
- 使用 `git submodule update --init --recursive`，不用 `--remote`。不要在服务器手工追踪插件分支最新头。
- 部署前备份数据库、产物与配置；按审查后的变更执行 SQL，构建/重启服务，检查代理解析及 feed/Range。
- 暂停 feed 不撤销已缓存包，卸载会破坏数据；二者都不是客户端自动降级保证。操作说明必须告知这些限制。

## 交付

列出变更文件、验证命令与结果，以及待用户确认的真实主站兼容性和发布信息。许可见 `LICENSE`，保留 `THIRD_PARTY_NOTICES.md` 上游声明；不得将衍生部分许可写成对上游的所有权声明。
