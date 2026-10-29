# 离线生成 release manifest v2

`../../scripts/generate_manifest.py` 仅依赖 Python 3.10+ 标准库，可单独复制到干净构建机执行，不需要主站代码、环境配置、数据库或网络。脚本不会执行 OS / Authenticode 验签，不访问服务器；只读取通过命令行显式指定的安装包、blockmap 和可选签名声明文件。

## 使用

以下命令从后端宿主根目录执行；若只克隆了独立插件仓库，将脚本路径改为 `scripts/generate_manifest.py`，产物路径替换为自己的构建输出：

```sh
python backend/plugin/app_update/scripts/generate_manifest.py \
  --application-key myapp \
  --version 1.2.3 \
  --installer dist/Myapp-1.2.3-win-x64.exe \
  --blockmap dist/Myapp-1.2.3-win-x64.exe.blockmap \
  --output dist/release-manifest-1.2.3.json
```

- 应用 key 与后端创建规则一致：2–64 个小写 ASCII 字母、数字、`_`、`-`，首字符为字母或数字。
- version 为严格三段 ASCII 数字 `x.y.z`，总长不超过后端字段限制 32；不支持 `v` 前缀、预发布或构建后缀。
- 文件名只将 key 的首字母大写，安装包必须为 `{Key}-{version}-win-x64.exe`，blockmap 必须为同名安装包加 `.blockmap`。输入必须是非空普通文件。
- 输出包含 `schemaVersion: 2`、`version`、`target: win32-x64`、`artifact`、`blockmap` 和 `signature`。安装包 SHA256 / SHA512（Base64）和 blockmap SHA256 均按 1 MiB 块流式计算，`bytes` 为实际读取字节数。构建产物应在生成期间保持不变。
- 默认 `signature` 为 `{"status": "unknown"}`。**unknown 不等于 unsigned，也不等于 valid**。
- 输出父目录须已存在且支持同目录硬链接（无 `--force` 时用于原子防覆盖发布）。已有输出默认拒绝，确认后可加 `--force`。即使加 `--force` 也不能覆盖任一输入（含符号链接和硬链接别名）；输出符号链接始终拒绝。先写同目录临时文件再发布，不留下半写入的 manifest。
- 参数或输入错误返回退出码 2，并在 stderr 输出 `error:`，不输出 Python traceback。

## 可选构建侧声明

通过 `--signature-file path/to/signature.json` 读取**扁平 JSON 对象**，不是整个 manifest：

```sh
python backend/plugin/app_update/scripts/generate_manifest.py \
  --application-key myapp --version 1.2.3 \
  --installer dist/Myapp-1.2.3-win-x64.exe \
  --blockmap dist/Myapp-1.2.3-win-x64.exe.blockmap \
  --output dist/release-manifest-1.2.3.json \
  --signature-file backend/plugin/app_update/examples/manifest/signature.example.json
```

声明文件最多 64 KiB，只接受白名单字段：`status`（非空字符串，最多 32 字符），以及 `publisherName`、`installerThumbprint`、`applicationThumbprint`、`timestampSubject`（字符串，各最多 1024 字符）。未知字段、非字符串（包括 null）、超长值或无效 JSON 均拒绝。缺少 `status` 时仍为 `unknown`，绝不会自动填 `valid`。状态是构建方原样提供的有限长度声明，不代表此脚本认可其真实性；真正验签应由可信构建流水线另行完成。

`signature.example.json` 中所有名称与指纹均为明显虚构占位文本，不含真实证书、签名或组织身份，状态为 `unknown`。它仅演示字段结构，请勿把示例当作验签证据。

生成后可按发布流程上传 installer、blockmap、manifest 三个文件；服务端会重新计算摘要，并调用 `validate_release_manifest` 校验。摘要匹配不是密码学签名验证。
