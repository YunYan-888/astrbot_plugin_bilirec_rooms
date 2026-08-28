import os
import asyncio
import aiohttp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core import AstrBotConfig


@register(
    "录播姬助手",
    "assistant",
    "录播姬助手：管理B站直播间录制",
    "1.6.0"
)
class BilirecRooms(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.api_url = config.get("api_url", "http://172.17.0.1:2356/api/room")
        self.auth_user = config.get("auth_user", "") or os.environ.get("BILIREC_USER", "")
        self.auth_pass = config.get("auth_pass", "") or os.environ.get("BILIREC_PASS", "")
        self.timeout = config.get("timeout", 10)
        self.compose_path = config.get("compose_path", "/opt/BililiveRecorder-webhook-docker")
        self.compose_file = config.get("compose_file", "compose.yml")
        self.restart_service = config.get("restart_service", "webhook")
        self.docker_sock = config.get("docker_sock", "/var/run/docker.sock")

        # 白名单：空列表表示所有人都可使用
        raw_whitelist = config.get("whitelist", [])
        if isinstance(raw_whitelist, str):
            raw_whitelist = [uid.strip() for uid in raw_whitelist.split(",") if uid.strip()]
        self.whitelist = set(str(uid).strip() for uid in raw_whitelist)
        self.whitelist_enabled = len(self.whitelist) > 0

        # 从配置读取指令名称
        self.cmd_help = config.get("cmd_help", "录播姬帮助")
        self.cmd_status = config.get("cmd_status", "查询录播姬")
        self.cmd_add = config.get("cmd_add", "添加录制")
        self.cmd_remove = config.get("cmd_remove", "删除录制")
        self.cmd_restart = config.get("cmd_restart", "重启录播姬")

    async def initialize(self):
        logger.info(
            f"[BiliRec] 插件已加载, API: {self.api_url}, "
            f"白名单: {'关闭(所有人可用)' if not self.whitelist_enabled else self.whitelist}, "
            f"指令: 帮助={self.cmd_help}, 查询={self.cmd_status}, "
            f"添加={self.cmd_add}, 删除={self.cmd_remove}, 重启={self.cmd_restart}"
        )

    async def terminate(self):
        pass

    def _check_permission(self, event: AstrMessageEvent) -> bool:
        if not self.whitelist_enabled:
            return True
        user_id = str(event.get_sender_id()).strip()
        if user_id not in self.whitelist:
            logger.warning(f"[BiliRec] 权限拒绝: 用户 {user_id} 不在白名单中")
            return False
        return True

    def _get_auth(self):
        if self.auth_user and self.auth_pass:
            return aiohttp.BasicAuth(self.auth_user, self.auth_pass)
        return None

    async def _resolve_room_id(self, keyword: str) -> tuple:
        """将昵称或房间号解析为实际房间号。返回 (room_id, error_msg)"""
        if keyword.isdigit():
            return int(keyword), None
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://search.bilibili.com/"
            }
            async with aiohttp.ClientSession() as session:
                search_url = "https://api.bilibili.com/x/web-interface/wbi/search/type"
                params = {"search_type": "bili_user", "keyword": keyword, "page": 1}
                async with session.get(search_url, params=params, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                    data = await resp.json()
                results = data.get("data", {}).get("result", [])
                if not results:
                    return None, f"未找到名为「{keyword}」的UP主"
                target = None
                for r in results:
                    if r.get("uname") == keyword:
                        target = r
                        break
                if not target:
                    target = results[0]
                mid = target.get("mid")
                uname = target.get("uname", keyword)
                room_url = "https://api.live.bilibili.com/room/v1/Room/getRoomInfoOld"
                async with session.get(room_url, params={"mid": mid}, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                    room_data = await resp.json()
                if room_data.get("code") != 0:
                    return None, f"获取UP主「{uname}」(UID:{mid}) 的直播间信息失败: {room_data.get('message')}"
                room_info = room_data.get("data", {})
                room_id = room_info.get("roomid")
                if not room_id:
                    return None, f"UP主「{uname}」(UID:{mid}) 没有开通直播间"
                logger.info(f"[BiliRec] 昵称解析: {keyword} → UP主:{uname}(UID:{mid}) → 房间号:{room_id}")
                return room_id, None
        except Exception as e:
            logger.error(f"[BiliRec] 昵称解析异常: {keyword}, {e}")
            return None, f"解析昵称「{keyword}」时出错: {str(e)}"

    def _extract_arg(self, raw: str, prefixes: list) -> tuple:
        """从原始消息中提取指令后的参数，强制要求空格分隔。
        返回 (arg_str, error_msg)，error_msg 为 None 表示成功。"""
        for prefix in prefixes:
            if raw.startswith(prefix):
                raw_after = raw[len(prefix):]
                if raw_after and not raw_after[0].isspace():
                    return None, f"⚠️ 指令与参数之间需要加空格，例如：{prefix} 22603245"
                return raw_after.strip(), None
        return None, None

    # ==================== 帮助指令 ====================
    @filter.command("录播姬帮助", alias={"录播姬指令", "bili_help", "rec_help"})
    async def show_help(self, event: AstrMessageEvent):
        """显示录播姬所有可用指令"""
        help_text = (
            "📖 录播姬控制指令：\n\n"
            f"• {self.cmd_status} - 查看运行状态及所有直播间录制情况\n"
            f"• {self.cmd_add} <房间号/UP主名> - 添加指定直播间到录制列表\n"
            f"  例：{self.cmd_add} 22603245 或 {self.cmd_add} 永雏塔菲\n"
            f"• {self.cmd_remove} <房间号/UP主名> - 从录制列表中移除指定直播间\n"
            f"  例：{self.cmd_remove} 22603245 或 {self.cmd_remove} 永雏塔菲\n"
            f"• {self.cmd_restart} - 重启录播姬 webhook 服务\n"
            f"• {self.cmd_help} - 显示本帮助信息"
        )
        yield event.plain_result(help_text)

    # ==================== 查询指令 ====================
    @filter.command("查询录播姬", alias={"录播姬状态", "录播状态", "bili_rec", "rec_status"})
    async def get_rec_status(self, event: AstrMessageEvent):
        """查询录播姬运行状态及所有直播间录制情况"""
        if not self._check_permission(event):
            yield event.plain_result("🚫 你没有权限使用此命令。")
            return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.api_url,
                    auth=self._get_auth(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 401:
                        yield event.plain_result("❌ 录播姬认证失败，请检查用户名和密码配置。")
                        return
                    resp.raise_for_status()
                    rooms = await resp.json()
            total = len(rooms)
            recording_count = sum(1 for r in rooms if r.get("recording"))
            streaming_count = sum(1 for r in rooms if r.get("streaming") and not r.get("recording"))
            lines = [
                "📺 录播姬运行状态：",
                f"  服务: ✅ 正常运行",
                f"  房间总数: {total}",
                f"  录制中: {recording_count} | 直播中(未录): {streaming_count} | 空闲: {total - recording_count - streaming_count}",
                "",
                "📋 直播间录制详情："
            ]
            if not rooms:
                lines.append("  当前没有已添加的房间。")
            else:
                for room in rooms:
                    name = room.get("name", "未知")
                    room_id = room.get("roomId", "?")
                    streaming = room.get("streaming", False)
                    recording = room.get("recording", False)
                    auto_record = room.get("autoRecord", False)
                    title = room.get("title", "无")
                    if recording:
                        status_icon = "🔴 录制中"
                    elif streaming:
                        status_icon = "🟢 直播中"
                    else:
                        status_icon = "⚪ 空闲"
                    auto_icon = "✅" if auto_record else "❌"
                    lines.append(
                        f"• {name} (ID:{room_id})\n"
                        f"  状态: {status_icon} | 自动录制: {auto_icon}\n"
                        f"  标题: {title}"
                    )
            yield event.plain_result("\n".join(lines))
        except aiohttp.ClientConnectorError:
            yield event.plain_result("❌ 无法连接录播姬服务，请检查服务是否运行及地址配置是否正确。")
        except Exception as e:
            logger.error(f"[BiliRec] 查询异常: {e}")
            yield event.plain_result(f"❌ 查询异常: {str(e)}")

    # ==================== 添加录制指令 ====================
    @filter.command("添加录制", alias={"添加录播", "add_rec", "rec_add"})
    async def add_room(self, event: AstrMessageEvent):
        """添加指定房间号或UP主昵称到录播姬录制列表"""
        if not self._check_permission(event):
            yield event.plain_result("🚫 你没有权限使用此命令。")
            return
        raw = event.message_str.strip()
        prefixes = [self.cmd_add, "添加录播", "add_rec", "rec_add"]
        arg, err = self._extract_arg(raw, prefixes)
        if err:
            yield event.plain_result(err)
            return
        if not arg:
            yield event.plain_result(f"⚠️ 请指定房间号或UP主昵称，例如：{self.cmd_add} 22603245 或 {self.cmd_add} 永雏塔菲")
            return
        room_id, resolve_err = await self._resolve_room_id(arg)
        if room_id is None:
            yield event.plain_result(f"⚠️ {resolve_err}")
            return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.api_url,
                    auth=self._get_auth(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    resp.raise_for_status()
                    rooms = await resp.json()
                existing = [r for r in rooms if r.get("roomId") == room_id]
                if existing:
                    name = existing[0].get("name", "未知")
                    yield event.plain_result(f"⚠️ 房间 {room_id} ({name}) 已在录制列表中，无需重复添加。")
                    return
                async with session.post(
                    self.api_url,
                    auth=self._get_auth(),
                    json={"roomId": room_id, "autoRecord": True},
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 401:
                        yield event.plain_result("❌ 录播姬认证失败，请检查用户名和密码配置。")
                        return
                    if resp.status in (200, 201):
                        result = await resp.json()
                        name = result.get("name", "未知")
                        logger.info(f"[BiliRec] 添加房间成功: {room_id} ({name})")
                        yield event.plain_result(f"✅ 已成功添加房间 {room_id} ({name}) 到录制列表！\n自动录制: ✅ 已开启")
                    else:
                        body = await resp.text()
                        logger.error(f"[BiliRec] 添加房间失败: HTTP {resp.status}, {body}")
                        yield event.plain_result(f"❌ 添加房间失败 (HTTP {resp.status}): {body}")
        except aiohttp.ClientConnectorError:
            yield event.plain_result("❌ 无法连接录播姬服务，请检查服务是否运行及地址配置是否正确。")
        except Exception as e:
            logger.error(f"[BiliRec] 添加房间异常: {e}")
            yield event.plain_result(f"❌ 添加房间异常: {str(e)}")

    # ==================== 删除录制指令 ====================
    @filter.command("删除录制", alias={"删除录播", "del_rec", "rec_del", "remove_rec"})
    async def remove_room(self, event: AstrMessageEvent):
        """从录播姬录制列表中移除指定房间"""
        if not self._check_permission(event):
            yield event.plain_result("🚫 你没有权限使用此命令。")
            return
        raw = event.message_str.strip()
        prefixes = [self.cmd_remove, "删除录播", "del_rec", "rec_del", "remove_rec"]
        arg, err = self._extract_arg(raw, prefixes)
        if err:
            yield event.plain_result(err)
            return
        if not arg:
            yield event.plain_result(f"⚠️ 请指定房间号或UP主昵称，例如：{self.cmd_remove} 22603245 或 {self.cmd_remove} 永雏塔菲")
            return
        room_id, resolve_err = await self._resolve_room_id(arg)
        if room_id is None:
            yield event.plain_result(f"⚠️ {resolve_err}")
            return
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.api_url,
                    auth=self._get_auth(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    resp.raise_for_status()
                    rooms = await resp.json()
                target = None
                for r in rooms:
                    if r.get("roomId") == room_id:
                        target = r
                        break
                if not target:
                    yield event.plain_result(f"⚠️ 未找到房间 {room_id}，该房间不在录制列表中。")
                    return
                object_id = target.get("objectId")
                name = target.get("name", "未知")
                delete_url = f"{self.api_url}/{object_id}"
                async with session.delete(
                    delete_url,
                    auth=self._get_auth(),
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 401:
                        yield event.plain_result("❌ 录播姬认证失败，请检查用户名和密码配置。")
                        return
                    if resp.status in (200, 204):
                        logger.info(f"[BiliRec] 删除房间成功: {room_id} ({name})")
                        yield event.plain_result(f"✅ 已成功从录制列表中移除房间 {room_id} ({name})！")
                    else:
                        body = await resp.text()
                        logger.error(f"[BiliRec] 删除房间失败: HTTP {resp.status}, {body}")
                        yield event.plain_result(f"❌ 删除房间失败 (HTTP {resp.status}): {body}")
        except aiohttp.ClientConnectorError:
            yield event.plain_result("❌ 无法连接录播姬服务，请检查服务是否运行及地址配置是否正确。")
        except Exception as e:
            logger.error(f"[BiliRec] 删除房间异常: {e}")
            yield event.plain_result(f"❌ 删除房间异常: {str(e)}")

    # ==================== 重启指令 ====================
    @filter.command("重启录播姬", alias={"重启录播", "restart_rec", "rec_restart"})
    async def restart_bilirec(self, event: AstrMessageEvent):
        """通过 docker.sock + docker-py 重启录播姬 webhook 服务"""
        if not self._check_permission(event):
            yield event.plain_result("🚫 你没有权限使用此命令。")
            return
        yield event.plain_result("🔄 正在通过 docker.sock 重启录播姬服务...")
        try:
            import docker
        except ImportError:
            logger.error("[BiliRec] docker SDK 未安装，请在容器内执行 pip install docker")
            yield event.plain_result("❌ 容器内缺少 docker SDK，请联系管理员安装。")
            return
        try:
            client = docker.DockerClient(base_url=f"unix://{self.docker_sock}")
            project_name = os.path.basename(os.path.normpath(self.compose_path))
            label_filter = f"com.docker.compose.service={self.restart_service}"
            containers = client.containers.list(filters={"label": label_filter})
            matched = [
                c for c in containers
                if c.labels.get("com.docker.compose.project") == project_name
            ]
            if not matched:
                matched = [
                    c for c in containers
                    if self.restart_service in c.name
                ]
            if not matched:
                available = [f"{c.name}({c.short_id})" for c in containers[:10]]
                msg = f"❌ 未找到服务 '{self.restart_service}' 对应的容器。\n"
                msg += f"项目名: {project_name}\n"
                msg += f"可用容器: {', '.join(available) if available else '无'}"
                logger.error(f"[BiliRec] {msg}")
                yield event.plain_result(msg)
                return
            target = matched[0]
            logger.info(f"[BiliRec] 找到目标容器: {target.name} ({target.short_id}), 执行 restart")
            target.restart(timeout=30)
            logger.info(f"[BiliRec] 容器 {target.name} 重启成功")
            yield event.plain_result(f"✅ 录播姬服务重启成功！\n容器: {target.name} ({target.short_id})")
        except docker.errors.APIError as e:
            logger.error(f"[BiliRec] Docker API 错误: {e}")
            yield event.plain_result(f"❌ Docker API 错误: {str(e)}")
        except FileNotFoundError:
            logger.error(f"[BiliRec] docker.sock 不存在: {self.docker_sock}")
            yield event.plain_result(f"❌ docker.sock 未找到 ({self.docker_sock})，请确认已挂载到容器内。")
        except PermissionError:
            logger.error(f"[BiliRec] docker.sock 权限不足: {self.docker_sock}")
            yield event.plain_result("❌ docker.sock 权限不足，请确认容器以 root 运行或 sock 文件权限正确。")
        except Exception as e:
            logger.error(f"[BiliRec] 重启异常: {e}")
            yield event.plain_result(f"❌ 重启异常: {str(e)}")
