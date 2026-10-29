# Nginx 更新源示例

`app_update.conf` 是 **server 级片段**，不是完整 `nginx.conf`。用于新建或调整开发环境／经审核的部署配置，不由插件自动修改宿主文件。

## 接入步骤

1. 确认后端实际写入目录，默认是 `backend/static/upload/app_updates/`。暂存与正式目录应在同一支持硬链接的本地文件系统，以支持原子防覆盖提交。Docker 下复用宿主已有上传卷；不要求新增卷或修改主项目挂载结构。
2. 确认 Nginx 对该目录的只读可见路径。示例使用 `/www/fba_server/backend/static/upload/app_updates/`，须按实际环境修改 `alias`。
3. 修改 `proxy_pass` 的后端地址。Docker 示例是 `http://fba_server:8001`；本地进程可改为实际后端监听地址。Nginx 在容器内时，`127.0.0.1` 指 Nginx 容器本身，不是宿主机。
4. 将片段合并进现有对外 `server {}`。删除已有冲突的 `/updates/` 规则；与通用正则规则并存时注意顺序。不要保留另一个 `location ^~ /updates/`，它会绕过这里的正则规则。
5. 若现有 `server` 已设置 `client_max_body_size` 或 `client_body_timeout`，合并成单一声明，不要重复 include。同样将上传超时合并到现有 API location，而非复制一个重复 location。
6. 每一层网关均需允许完整 multipart 请求（默认安装包 512 MiB + blockmap 10 MiB + manifest 1 MiB，加边界开销），示例设为 1 GiB。将客户端上传、后端和代理超时一起设置为合适值；前端上传超时为 30 分钟。
7. `nginx -t` 成功后按宿主部署流程重载。在生产环境不直接编辑 Git 管理文件，先在开发侧提交配置再部署。
8. 将 `APP_UPDATE_PUBLIC_BASE_URL` 改为实际 `https://example.org/updates`，后端重启，前端重新构建。域名示例不能原样用于真实客户端。

## 路由与安全边界

- `latest.yml` 由后端动态生成，不落盘、不在代理缓存；启用状态、版本状态和限流由后端决定。
- 安装包和 blockmap 通过白名单静态下载，支持 Nginx 默认的 GET、HEAD、Range；没有启用 `max_ranges 0` 或关闭断点续传。
- `/updates/` 下其他路径统一 404，包括 `.staging`、release manifest JSON、任意目录文件；不要用宽泛的 `alias` 覆盖白名单。
- 缓存只用于成功下载的不可变文件，不给 404 添加一年缓存。已经被客户端或 CDN 缓存的安装包不会因“暂停版本”自动消失。
- **产物不是保密数据。** 上传完成就已在静态目录中，即使版本仍是草稿，知道 URL 的人也可能下载。暂停只撤回 feed，不是下载鉴权／撤包功能。
- 宿主可能另行暴露 `/static/upload/`，应核查它是否绕过这里的保护并暴露 staging 或 manifest。如需保护这类信息，需在宿主的静态路由和反向代理统一限制，不能只依赖本片段。
- 外层代理应正确传递客户端地址，后端只信任已知代理。否则 IP 限流可能把所有客户端算为同一来源。

## 本地验证

在隔离应用 `demo` 的 stable 渠道发布一个真实可用版本（下面以 `0.1.0` 为例）：

```bash
curl -i https://example.org/updates/demo/stable/latest.yml
curl -I https://example.org/updates/demo/stable/Demo-0.1.0-win-x64.exe
curl -i -H 'Range: bytes=0-15' https://example.org/updates/demo/stable/Demo-0.1.0-win-x64.exe
curl -i https://example.org/updates/.staging/probe
curl -i https://example.org/updates/demo/stable/release-manifest-0.1.0.json
```

期望：YAML 返回 200 且不缓存，HEAD 返回文件长度，Range 返回 206 和正确的 `Content-Range`，最后两项返回 404。未发布／暂停唯一版本后 YAML 返回 404，但已有静态包仍可能可下载。

只启动 FastAPI 会提供管理 API 和 `latest.yml`，**不会自动提供 `/updates/` 安装包下载**。完整 Electron 联调需要上述代理／静态映射。容器 IP 变化后，是否重载 Nginx DNS 由宿主部署策略负责。
