import asyncio
from typing import List
from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger
from .data_manager import DataManager
from .utils import CommandUtils
from .command_executor import CommandExecutor


class CommandProcessor:
    def __init__(self, star_instance):
        self.star = star_instance
        self.context = star_instance.context
        self.data_manager = star_instance.data_manager
        self.command_executor = CommandExecutor(self.context)

    def _resolve_wake_prefixes(self, event: AstrMessageEvent) -> List[str]:
        """解析当前会话可用的主框架唤醒前缀列表。"""
        config = {}

        if hasattr(self.context, "get_config"):
            try:
                config = self.context.get_config(umo=event.unified_msg_origin)
            except TypeError:
                config = self.context.get_config()
            except Exception:
                logger.warning("读取会话配置失败，回退读取全局配置")
                try:
                    config = self.context.get_config()
                except Exception:
                    config = {}

        if hasattr(config, "get"):
            raw_prefixes = config.get("wake_prefix", ["/"])
        else:
            raw_prefixes = ["/"]

        if isinstance(raw_prefixes, str):
            prefixes = [raw_prefixes]
        elif isinstance(raw_prefixes, list):
            prefixes = [str(prefix) for prefix in raw_prefixes]
        else:
            prefixes = ["/"]

        normalized = [prefix for prefix in prefixes if prefix is not None]
        return normalized or ["/"]

    async def execute_command(self, event, command_text: str, args: str = "") -> str:
        """执行指令"""
        try:
            if not self.data_manager.is_plugin_enabled():
                return "插件当前已禁用，请在 WebUI 的 basic_config.enable_plugin 中开启后再试。"

            # 查找指令映射
            mapping = self.data_manager.get_mapping(command_text)
            if not mapping:
                return f"错误：未找到指令 '{command_text}' 的映射。请先使用 add_command_mapping 添加映射。"

            llm_function = mapping.get("llm_function")
            description = mapping.get("description", "")

            logger.info(f"执行指令映射: {command_text} -> {llm_function}")

            # 构建完整指令（自动匹配 AstrBot 主框架 wake_prefix）
            wake_prefixes = self._resolve_wake_prefixes(event)
            already_prefixed = any(
                prefix and command_text.startswith(prefix) for prefix in wake_prefixes
            )
            if already_prefixed:
                full_command = command_text
            else:
                full_command = f"{wake_prefixes[0]}{command_text}"

            logger.info(
                f"执行指令前缀解析: wake_prefixes={wake_prefixes}, 使用命令={full_command}"
            )

            if args:
                full_command += f" {args}"

            # 获取用户信息
            creator_id = (
                event.get_sender_id() if hasattr(event, "get_sender_id") else "user"
            )
            creator_name = None
            if hasattr(event, "message_obj") and hasattr(event.message_obj, "sender"):
                creator_name = event.message_obj.sender.nickname

            capture_timeout = self.data_manager.get_capture_timeout()
            wait_interval = min(0.5, max(0.05, capture_timeout / 200))
            forward_interval = self.data_manager.get_forward_interval()
            response_mode = self.data_manager.get_response_mode()

            # 使用指令执行器执行指令
            (
                success,
                captured_messages,
            ) = await self.command_executor.execute_command_with_options(
                event.unified_msg_origin,
                full_command,
                creator_id,
                creator_name,
                capture_timeout=capture_timeout,
                wait_interval=wait_interval,
            )

            if success and captured_messages:
                if response_mode in {"forward_and_text", "forward_only"}:
                    logger.info(
                        f"[command_processor] 开始主动发送转发消息，mode={response_mode}"
                    )

                    for i, captured_msg in enumerate(captured_messages):
                        if captured_msg is not None:
                            logger.info(
                                f"[command_processor] 发送第 {i + 1} 条转发消息"
                            )

                            # 构建转发消息
                            from astrbot.core.message.message_event_result import (
                                MessageChain,
                            )
                            from astrbot.api.message_components import Plain

                            forward_msg = MessageChain()
                            forward_msg.chain.append(
                                Plain(f"[指令执行] {command_text}\n")
                            )

                            # 添加捕获到的消息内容
                            if hasattr(captured_msg, "chain") and captured_msg.chain:
                                for component in captured_msg.chain:
                                    forward_msg.chain.append(component)

                            # 发送转发消息
                            await self.context.send_message(
                                event.unified_msg_origin, forward_msg
                            )

                            # 如果有多条消息，添加间隔
                            if (
                                len(captured_messages) > 1
                                and i < len(captured_messages) - 1
                            ):
                                await asyncio.sleep(forward_interval)

                # 提取响应文本用于返回给LLM函数
                response_texts = []
                for msg_chain in captured_messages:
                    if msg_chain is not None:
                        # 尝试不同的方法获取文本
                        text = None
                        if hasattr(msg_chain, "get_plain_text"):
                            text = msg_chain.get_plain_text()
                        elif hasattr(msg_chain, "to_plain_text"):
                            text = msg_chain.to_plain_text()
                        elif hasattr(msg_chain, "chain") and msg_chain.chain:
                            # 手动提取文本
                            text_parts = []
                            for component in msg_chain.chain:
                                if hasattr(component, "text"):
                                    text_parts.append(component.text)
                                elif hasattr(component, "content"):
                                    text_parts.append(component.content)
                            text = "".join(text_parts) if text_parts else None

                        if text:
                            response_texts.append(text)

                if response_texts:
                    if response_mode == "forward_only":
                        return f"指令 '{command_text}' 执行成功，结果已转发到会话"
                    return f"指令 '{command_text}' 执行结果：\n" + "\n".join(
                        response_texts
                    )
                else:
                    return f"指令 '{command_text}' 执行成功，但未返回文本内容"
            else:
                return f"指令 '{command_text}' 执行失败或超时"

        except Exception as e:
            logger.error(f"执行指令失败: {e}")
            return f"执行指令时发生错误：{str(e)}"

    async def add_mapping(
        self, event, command_name: str, llm_function: str, description: str = ""
    ):
        """添加指令映射"""
        logger.info(
            f"[command_processor] add_mapping 被调用 - 指令: '{command_name}', 函数: '{llm_function}', 描述: '{description}'"
        )

        try:
            if not self.data_manager.is_plugin_enabled():
                yield event.plain_result(
                    "插件当前已禁用，请在 WebUI 中开启后再管理映射"
                )
                return

            success, message = self.data_manager.add_mapping(
                command_name, llm_function, description
            )
            logger.info(
                f"[command_processor] data_manager.add_mapping 返回: success={success}, message='{message}'"
            )

            if success and self.data_manager.should_auto_refresh_on_change():
                logger.info(f"[command_processor] 开始刷新动态LLM函数")
                # 刷新动态LLM函数
                self.star.dynamic_llm_manager.refresh_functions()
                logger.info(f"[command_processor] 动态LLM函数刷新完成")

            yield event.plain_result(message)

        except Exception as e:
            logger.error(f"[command_processor] 添加指令映射失败: {e}")
            import traceback

            logger.error(f"[command_processor] 错误堆栈:\n{traceback.format_exc()}")
            yield event.plain_result(f"添加指令映射时发生错误：{str(e)}")

    async def list_mappings(self, event, state_filter: str = "all"):
        """列出所有指令映射"""
        try:
            if not self.data_manager.is_plugin_enabled():
                yield event.plain_result(
                    "插件当前已禁用，请在 WebUI 中开启后再查看映射"
                )
                return

            normalized_filter = state_filter.strip().lower() if state_filter else "all"
            alias_map = {
                "all": "all",
                "--all": "all",
                "enabled": "enabled",
                "--enabled": "enabled",
                "disabled": "disabled",
                "--disabled": "disabled",
            }
            if normalized_filter not in alias_map:
                yield event.plain_result(
                    "过滤参数无效，可用值：--enabled / --disabled / --all"
                )
                return
            normalized_filter = alias_map[normalized_filter]

            mappings = self.data_manager.list_mappings(state_filter=normalized_filter)
            if not mappings:
                empty_text = {
                    "all": "当前没有配置任何指令映射",
                    "enabled": "当前没有已启用的指令映射",
                    "disabled": "当前没有已禁用的指令映射",
                }
                yield event.plain_result(empty_text[normalized_filter])
                return

            title_map = {
                "all": "当前配置的指令映射：",
                "enabled": "当前已启用的指令映射：",
                "disabled": "当前已禁用的指令映射：",
            }
            result = title_map[normalized_filter] + "\n"
            for i, (cmd, mapping) in enumerate(mappings.items(), 1):
                llm_func = mapping.get("llm_function", "")
                desc = mapping.get("description", "")
                enabled = mapping.get("enabled", True)
                result += f"{i}. {cmd} -> {llm_func}"
                if desc:
                    result += f" ({desc})"
                if not enabled:
                    result += " [已禁用]"
                result += "\n"

            yield event.plain_result(result)
        except Exception as e:
            logger.error(f"列出指令映射失败: {e}")
            yield event.plain_result(f"列出指令映射时发生错误：{str(e)}")

    async def remove_mapping(self, event, command_name: str):
        """删除指令映射"""
        try:
            if not self.data_manager.is_plugin_enabled():
                yield event.plain_result(
                    "插件当前已禁用，请在 WebUI 中开启后再管理映射"
                )
                return

            success = self.data_manager.remove_mapping(command_name)
            if success:
                # 刷新动态LLM函数
                if self.data_manager.should_auto_refresh_on_change():
                    self.star.dynamic_llm_manager.refresh_functions()
                yield event.plain_result(f"成功删除指令映射：'{command_name}'")
            else:
                yield event.plain_result(f"错误：指令 '{command_name}' 不存在映射")
        except Exception as e:
            logger.error(f"删除指令映射失败: {e}")
            yield event.plain_result(f"删除指令映射时发生错误：{str(e)}")

    async def set_mapping_enabled(self, event, command_name: str, enabled: bool):
        """设置映射启用状态"""
        try:
            if not self.data_manager.is_plugin_enabled():
                yield event.plain_result(
                    "插件当前已禁用，请在 WebUI 中开启后再管理映射"
                )
                return

            success, message = self.data_manager.set_mapping_enabled(
                command_name, enabled
            )
            if success and self.data_manager.should_auto_refresh_on_change():
                self.star.dynamic_llm_manager.refresh_functions()

            yield event.plain_result(message)
        except Exception as e:
            action = "启用" if enabled else "禁用"
            logger.error(f"{action}指令映射失败: {e}")
            yield event.plain_result(f"{action}指令映射时发生错误：{str(e)}")
