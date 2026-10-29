# Changelog

## 0.2.0 — 首次公开源码导入

### 公开发布准备

- 前后端配套目标版本为后端 `app_update 0.2.0` / 前端 `app_update_ui 0.2.0`，采用 MIT，保留适用上游声明。
- 补齐 CLI Git/ZIP、submodule 和手工安装、卸载、固定 SHA 部署、安全边界与干净主站验收文档。
- 插件独立 `AppUpdateSettings` 提供环境变量 > `.env` > TOML 优先级与六字段校验，无需修改宿主 conf；变更配置需重启。
- 标准 init/destroy 按官方插件 SQL 解析器约定组织，CLI ORM 先建表；手工 DDL 独立为 schema 文件，手工安装先 schema 再 init。重复 seed 不覆盖已有数据。
- 提供 manifest 生成器及示例，默认签名状态 `unknown`；声明不等于系统验签，不自动判定 `valid`。
- Nginx 示例限定 server 级 include，仅公开安装包/blockmap 白名单、代理动态 feed，其余更新路径 404。
- 只读签名信息在历史 manifest 缺失或不合规时降级为空，不影响列表/详情，不修改原始签名状态。
- 雪花主键和关联 ID 对外使用字符串，配套前端无损保留 ID；自增初始化不分配巨大固定 ID。
- 暂停历史非当前版本不再切换当前更新源；卸载前显式阻止外部自定义子菜单成为孤儿。
- 上传写入使用异步文件 IO，正式产物使用原子 no-clobber 提交，防止并发覆盖；需要同一支持硬链接的文件系统。
- 兼容 FBA 1.16 Redis SDK 与旧版宿主限流接口，不强制新宿主安装旧 `pyrate-limiter`。
- 产物按版本删除显式使用批量模式，修复三产物删除时 CRUDPlus 单条保护报错。
- 显式声明 PyYAML；配套 UI 在插件工作区声明 Vue Test Utils 开发依赖。

### 升级注意

- 现有 0.1 数据库无需结构迁移，不回填历史签名信息。升级前备份数据库与产物，更新前后端并重启/重建；核对配置校验和 Nginx 映射。
- 不在现有数据库执行 `fba init`（会 drop_all）。新安装按 README 选择安装路径。
- 当前目标仅 Windows x64 NSIS，严格 `x.y.z` 及 key 首字母大写的文件名契约；electron-builder 默认命名不保证匹配。

### 验证状态

官方 FBA 1.16.0 / PostgreSQL 17.4 自增模式的实测范围见 [验收记录](docs/VALIDATION_2026-10-28.md)，不扩大到其他数据库、主键或客户端。

自动化测试覆盖项和真实部署验收分开记录。不得据此条目推断所有测试已通过或已有特定 FBA/Electron 版本兼容认证；实际命令和结果以当前提交测试日志为准。[干净主站验收](docs/CLEAN_HOST_VALIDATION.md) 中的双数据库 × 双主键、前端权限、真实下载/Range 与卸载仍待用户记录验收，不作为已完成事项。

当前为首次公开源码导入，不承诺已创建版本标签、GitHub Release 或安装附件，也不表示完成全部部署验收。源码安装地址见 README。

## 0.1 — 既有基线

既有多应用/渠道、版本发布与暂停回退、三产物校验及 generic feed 能力。未在此补造历史发布日期、提交标签或部署验收记录。
