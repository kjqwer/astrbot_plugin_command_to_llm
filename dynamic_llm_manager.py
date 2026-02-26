import asyncio
from typing import Dict, List, Optional
from astrbot.api import logger
from astrbot.api.star import Context
from .data_manager import DataManager
from .command_processor import CommandProcessor


class DynamicLLMManager:
    """动态LLM函数管理器，用于动态注册和管理LLM函数"""

    def __init__(
        self,
        context: Context,
        data_manager: DataManager,
        command_processor: CommandProcessor,
    ):
        self.context = context
        self.data_manager = data_manager
        self.command_processor = command_processor
        self.registered_functions = set()  # 记录已注册的函数名

    def register_dynamic_functions(self):
        """注册所有动态LLM函数"""
        try:
            if not self.data_manager.is_plugin_enabled():
                logger.info("插件处于禁用状态，跳过动态LLM函数注册")
                return

            mappings = self.data_manager.list_mappings(enabled_only=True)
            for command_name, mapping in mappings.items():
                llm_function = mapping.get("llm_function")
                description = mapping.get("description", "")

                if llm_function and llm_function not in self.registered_functions:
                    self._register_single_function(
                        command_name, llm_function, description
                    )
                    self.registered_functions.add(llm_function)
                    logger.info(f"动态注册LLM函数: {llm_function} -> {command_name}")

        except Exception as e:
            logger.error(f"注册动态LLM函数失败: {e}")

    def _register_single_function(
        self, command_name: str, llm_function: str, description: str
    ):
        """注册单个LLM函数"""
        logger.info(
            f"[dynamic_llm_manager] 注册单个LLM函数: {llm_function} -> {command_name}"
        )

        try:
            # 创建函数参数定义
            mapping = self.data_manager.get_mapping(command_name, enabled_only=False)
            specific_arg_desc = (
                str(mapping.get("arg_description", "")).strip() if mapping else ""
            )
            default_arg_desc = self.data_manager.get_default_arg_description()
            arg_description = specific_arg_desc or default_arg_desc

            func_args = [
                {
                    "type": "string",
                    "name": "command_text",
                    "description": f"要执行的指令，固定值为 '{command_name}'",
                },
                {
                    "type": "string",
                    "name": "args",
                    "description": arg_description or "指令参数，可选",
                },
            ]

            # 创建函数描述
            global_tool_desc = self.data_manager.get_tool_description()
            func_desc = f"执行指令 '{command_name}'"
            if description:
                func_desc += f"，{description}"
            if global_tool_desc:
                func_desc += f"。{global_tool_desc}"

            logger.info(f"[dynamic_llm_manager] 创建函数参数: {func_args}")
            logger.info(f"[dynamic_llm_manager] 函数描述: {func_desc}")

            # 创建动态处理器
            handler = self._create_dynamic_handler(command_name)
            logger.info(f"[dynamic_llm_manager] 动态处理器创建完成: {handler}")

            # 注册到LLM工具管理器
            logger.info(f"[dynamic_llm_manager] 开始注册到LLM工具管理器")
            # 直接使用 add_func 方法，绕过 context.register_llm_tool 的bug
            self.context.provider_manager.llm_tools.add_func(
                llm_function, func_args, func_desc, handler
            )
            logger.info(f"[dynamic_llm_manager] LLM函数注册完成: {llm_function}")

        except Exception as e:
            logger.error(f"[dynamic_llm_manager] 注册LLM函数 {llm_function} 失败: {e}")
            import traceback

            logger.error(f"[dynamic_llm_manager] 错误堆栈:\n{traceback.format_exc()}")

    def _create_dynamic_handler(self, command_name: str):
        """创建动态处理函数"""
        logger.info(f"[dynamic_llm_manager] 创建动态处理函数: {command_name}")

        async def dynamic_handler(event, **kwargs):
            logger.info(
                f"[dynamic_llm_manager] 动态函数 {command_name} 被调用，参数: {kwargs}"
            )

            # 获取参数
            command_text = kwargs.get("command_text", command_name)
            args = kwargs.get("args", "")

            # 确保command_text是固定的指令名
            if command_text != command_name:
                command_text = command_name

            logger.info(
                f"[dynamic_llm_manager] 执行指令: '{command_text}', 参数: '{args}'"
            )

            try:
                result = await self.command_processor.execute_command(
                    event, command_text, args
                )
                logger.info(
                    f"[dynamic_llm_manager] 指令执行完成，结果长度: {len(str(result))}"
                )

                response_mode = self.data_manager.get_response_mode()
                if response_mode == "forward_only":
                    # 对齐 astrbot_plugin_opencode：工具自行发送结果，避免触发额外 LLM 复述
                    return

                # 仅在允许文本回传时，把结果返回给 LLM
                return f"指令执行结果：{result}"

            except Exception as e:
                logger.error(f"[dynamic_llm_manager] 动态函数执行失败: {e}")
                import traceback

                logger.error(
                    f"[dynamic_llm_manager] 错误堆栈:\n{traceback.format_exc()}"
                )
                raise

        # 设置函数名和文档字符串
        safe_name = command_name.replace(" ", "_").replace("-", "_")
        dynamic_handler.__name__ = f"dynamic_{safe_name}"
        dynamic_handler.__doc__ = f"""执行指令 {command_name}
        
        Args:
            command_text(string): 要执行的指令，固定值为 '{command_name}'
            args(string): 指令参数，可选
        """

        logger.info(
            f"[dynamic_llm_manager] 动态处理函数创建完成: {dynamic_handler.__name__}"
        )
        return dynamic_handler

    def unregister_function(self, llm_function: str):
        """注销LLM函数"""
        try:
            if llm_function in self.registered_functions:
                self.context.unregister_llm_tool(llm_function)
                self.registered_functions.remove(llm_function)
                logger.info(f"注销LLM函数: {llm_function}")
        except Exception as e:
            logger.error(f"注销LLM函数 {llm_function} 失败: {e}")

    def refresh_functions(self):
        """刷新所有动态函数"""
        logger.info(f"[dynamic_llm_manager] 开始刷新动态LLM函数")

        try:
            # 注销所有已注册的函数
            logger.info(
                f"[dynamic_llm_manager] 注销已注册的 {len(self.registered_functions)} 个函数"
            )
            for func_name in list(self.registered_functions):
                self.unregister_function(func_name)

            # 重新注册所有函数
            logger.info(f"[dynamic_llm_manager] 重新注册所有函数")
            self.register_dynamic_functions()

            logger.info(
                f"[dynamic_llm_manager] 刷新动态LLM函数完成，当前注册了 {len(self.registered_functions)} 个函数"
            )

        except Exception as e:
            logger.error(f"[dynamic_llm_manager] 刷新动态LLM函数失败: {e}")
            import traceback

            logger.error(f"[dynamic_llm_manager] 错误堆栈:\n{traceback.format_exc()}")

    def get_registered_functions(self) -> List[str]:
        """获取已注册的函数列表"""
        return list(self.registered_functions)
