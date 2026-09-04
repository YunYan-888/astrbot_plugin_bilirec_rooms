# 录播姬助手

> 作者QQ：1361485017


AstrBot 插件，用于通过聊天指令管理 BililiveRecorder（录播姬）的直播间录制任务。
录播姬请自行拉取镜像下载。

> ⚠️ **适配说明**：本插件仅在 Linux 环境下配合 QQ 消息平台进行过测试，其他操作系统或消息平台可能存在兼容性问题，欢迎反馈。

## 功能特性

- 查询录播姬运行状态及所有直播间录制详情
- 添加直播间到录制列表（支持房间号或 UP 主昵称），自动开启录制
- 从录制列表中移除直播间（支持房间号或 UP 主昵称）
- 重启录播姬 webhook 服务
- 可配置的指令名称和白名单权限控制
- 开启/关闭指定直播间的自动录制
- 手动开始/停止录制指定直播间（含开播状态和录制状态校验）
- 重启服务支持自动识别录播姬容器（无需填写服务名）
- 开启/关闭指定直播间的自动录制
- 手动开始/停止录制指定直播间（含开播状态和录制状态校验）
- 重启服务支持自动识别录播姬容器（无需填写服务名）

## 配置说明

在 AstrBot 控制台的插件配置页面中修改以下参数：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `api_url` | string | `http://172.17.0.1:2356/api/room` | 录播姬 WebAPI 的房间列表接口地址 |
| `auth_user` | string | （空） | HTTP Basic Auth 用户名，留空则读取环境变量 `BILIREC_USER` |
| `auth_pass` | string | （空） | HTTP Basic Auth 密码，留空则读取环境变量 `BILIREC_PASS` |
| `timeout` | int | `10` | API 请求超时时间（秒） |
| `compose_path` | string | `/opt/BililiveRecorder-webhook-docker` | docker compose 工作目录绝对路径 |
| `compose_file` | string | `compose.yml` | compose 配置文件名 |
| `restart_service` | string | （空） | docker compose 中要重启的服务名。**留空则自动查找**包含 BililiveRecorder 的容器 |
| `docker_sock` | string | `/var/run/docker.sock` | 容器内 docker.sock 挂载路径 |
| `whitelist` | list | `[]` | 用户 ID 白名单。**留空表示所有人都可使用**；填写后仅列表中的用户可执行操作 |
| `cmd_help` | string | `录播姬帮助` | 帮助指令名称 |
| `cmd_status` | string | `查询录播姬` | 查询状态指令名称 |
| `cmd_add` | string | `添加录制` | 添加录制指令名称（不含参数） |
| `cmd_remove` | string | `删除录制` | 删除录制指令名称（不含参数） |
| `cmd_restart` | string | `重启录播姬` | 重启服务指令名称 |
| `cmd_auto_on` | string | `开启自动录制` | 开启自动录制指令名称 |
| `cmd_auto_off` | string | `关闭自动录制` | 关闭自动录制指令名称 |
| `cmd_start_rec` | string | `开始录制` | 手动开始录制指令名称 |
| `cmd_stop_rec` | string | `停止录制` | 手动停止录制指令名称 |

### 关于白名单

- **留空**（默认）：所有用户均可使用全部指令
- **填写用户 ID**：仅白名单中的用户可执行 `查询录播姬`、`添加录制`、`删除录制`、`重启录播姬` 操作
- `录播姬帮助` 指令不受白名单限制，任何人可查看

### 关于自定义指令

修改 `cmd_help`、`cmd_status`、`cmd_add`、`cmd_remove`、`cmd_restart`、`cmd_auto_on`、`cmd_auto_off`、`cmd_start_rec`、`cmd_stop_rec` 的值即可更改触发关键词。修改后需重启 AstrBot 生效。注意：`@filter.command` 装饰器中的硬编码名称仍作为底层匹配，配置中的名称用于帮助文本显示和参数解析前缀匹配。

## 指令使用方法

> ⚠️ **重要**：带参数的指令，指令与参数之间**必须加空格**。

### 录播姬帮助
```
录播姬帮助
```
显示所有可用指令及示例。

### 查询录播姬
```
查询录播姬
```
查看录播姬服务状态、房间总数、录制中/直播中/空闲数量，以及每个直播间的详细信息（名称、房间号、状态、自动录制开关、直播标题）。

### 添加录制
```
添加录制 <房间号>
添加录制 <UP主昵称>
```
将指定直播间添加到录制列表并自动开启录制。

示例：
```
添加录制 22603245
添加录制 永雏塔菲
```

### 删除录制
```
删除录制 <房间号>
删除录制 <UP主昵称>
```
从录制列表中移除指定直播间。

示例：
```
删除录制 22603245
删除录制 永雏塔菲
```

### 重启录播姬
```
重启录播姬
```
通过 docker.sock 重启录播姬 webhook 服务容器。需要容器内安装 `docker` Python SDK 且 docker.sock 已正确挂载。

## 常见问题

### 认证失败
检查 `auth_user` 和 `auth_pass` 是否与录播姬设置的 HTTP Basic Auth 凭据一致。也可通过环境变量 `BILIREC_USER` / `BILIREC_PASS` 设置。

### 无法连接录播姬服务
确认 `api_url` 地址正确且录播姬服务正在运行。Docker 环境下通常使用 `http://172.17.0.1:端口/api/room`。

### 重启失败
确认 docker.sock 已挂载到 AstrBot 容器内，且容器以 root 运行或有足够权限访问 docker.sock。

### 昵称解析不准确
UP 主昵称需与 B 站用户名**完全匹配**。若存在同名用户，优先精确匹配，否则取搜索结果第一个。建议直接使用房间号以避免歧义。

## 更新日志

更新内容请查看 [CHANGELOG.md](CHANGELOG.md)
