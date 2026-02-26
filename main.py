from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import *
from astrbot.api.event.filter import command, command_group
from astrbot.api import logger, AstrBotConfig
from .command_processor import CommandProcessor
from .data_manager import DataManager
from .dynamic_llm_manager import DynamicLLMManager


@register("command_to_llm", "kjqwdw", "将指令转换为LLM函数调用", "1.1.0")
class CommandToLLM(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config if config is not None else {}

        # 初始化数据管理器
        self.data_manager = DataManager(context, self.config)

        # 初始化指令处理器
        self.command_processor = CommandProcessor(self)

        # 初始化动态LLM管理器
        self.dynamic_llm_manager = DynamicLLMManager(
            context, self.data_manager, self.command_processor
        )

        # 注册动态LLM函数
        self.dynamic_llm_manager.register_dynamic_functions()

        logger.info(
            f"指令转LLM插件启动成功，已加载 {len(self.data_manager.list_mappings())} 个映射，"
            f"已启用 {len(self.data_manager.list_mappings(enabled_only=True))} 个映射，"
            f"注册了 {len(self.dynamic_llm_manager.get_registered_functions())} 个动态LLM函数"
        )

    # 命令组定义
    @command_group("cmd2llm")
    def cmd2llm(self):
        """指令转LLM相关命令"""
        pass

    @cmd2llm.command("add")
    async def add_mapping(
        self,
        event: AstrMessageEvent,
        command_str: str,
        llm_function: str,
        description: str = "",
    ):
        """添加指令映射

        格式：/cmd2llm add <指令名> <LLM函数名> [描述]
        示例：/cmd2llm add rmd--ls list_reminders 列出所有提醒
        """
        logger.info(
            f"[command_to_llm] add_mapping 被调用，command_str: '{command_str}', llm_function: '{llm_function}', description: '{description}'"
        )

        # 解析指令名（将 -- 替换为空格）
        command_name = command_str.replace("--", " ")

        logger.info(
            f"[command_to_llm] 解析结果 - 指令名: '{command_name}', LLM函数: '{llm_function}', 描述: '{description}'"
        )

        try:
            async for result in self.command_processor.add_mapping(
                event, command_name, llm_function, description
            ):
                yield result
        except Exception as e:
            logger.error(f"[command_to_llm] add_mapping 调用失败: {e}")
            import traceback

            logger.error(f"[command_to_llm] 错误堆栈:\n{traceback.format_exc()}")
            yield event.plain_result(f"添加映射时发生错误：{str(e)}")

    @cmd2llm.command("ls")
    async def list_mappings(self, event: AstrMessageEvent, state_filter: str = "--all"):
        """列出所有指令映射

        格式：/cmd2llm ls [--enabled|--disabled|--all]
        示例：/cmd2llm ls --enabled
        """
        async for result in self.command_processor.list_mappings(event, state_filter):
            yield result

    @cmd2llm.command("rm")
    async def remove_mapping(self, event: AstrMessageEvent, command_str: str):
        """删除指令映射

        Args:
            command_str: 指令名称（支持 -- 连接）
        """
        # 解析指令名（将 -- 替换为空格）
        command_name = command_str.replace("--", " ")
        async for result in self.command_processor.remove_mapping(event, command_name):
            yield result

    @cmd2llm.command("enable")
    async def enable_mapping(self, event: AstrMessageEvent, command_str: str):
        """启用指令映射

        格式：/cmd2llm enable <指令名>
        示例：/cmd2llm enable rmd--ls
        """
        command_name = command_str.replace("--", " ")
        async for result in self.command_processor.set_mapping_enabled(
            event, command_name, True
        ):
            yield result

    @cmd2llm.command("disable")
    async def disable_mapping(self, event: AstrMessageEvent, command_str: str):
        """禁用指令映射

        格式：/cmd2llm disable <指令名>
        示例：/cmd2llm disable rmd--ls
        """
        command_name = command_str.replace("--", " ")
        async for result in self.command_processor.set_mapping_enabled(
            event, command_name, False
        ):
            yield result

    @cmd2llm.command("exec")
    async def execute_cmd(
        self, event: AstrMessageEvent, command_str: str, args: str = ""
    ):
        """执行指令

        格式：/cmd2llm exec <指令名> [参数]
        示例：/cmd2llm exec rmd--ls
        """
        # 解析指令名（将 -- 替换为空格）
        command_text = command_str.replace("--", " ")

        async for result in self.command_processor.execute_command(
            event, command_text, args
        ):
            yield result

    @cmd2llm.command("help")
    async def show_help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        help_text = """指令转LLM插件帮助：

/cmd2llm add <指令名> <LLM函数名> [描述] - 添加指令映射
/cmd2llm ls [--enabled|--disabled|--all] - 列出映射（支持状态过滤）
/cmd2llm rm <指令名> - 删除指令映射
/cmd2llm enable <指令名> - 启用指令映射
/cmd2llm disable <指令名> - 禁用指令映射
/cmd2llm exec <指令名> [参数] - 执行指令
/cmd2llm refresh - 刷新动态LLM函数
/cmd2llm help - 显示此帮助

指令名格式：
- 单个指令：rmd
- 多级指令：rmd--ls, rmd--add, rmd--help
- 支持任意数量的 -- 连接

动态LLM函数：
添加映射后会自动注册对应的LLM函数，如：
- 映射 "rmd ls" -> "list_reminders" 会注册 list_reminders 函数
- 映射 "rmd help" -> "show_help" 会注册 show_help 函数

示例：
/cmd2llm add rmd--ls list_reminders 列出所有提醒
/cmd2llm ls --enabled
/cmd2llm add rmd--add add_reminder 添加提醒
/cmd2llm exec rmd--ls
/cmd2llm exec rmd--add text=喝水 time=10:00
"""
        yield event.plain_result(help_text)

    @cmd2llm.command("refresh")
    async def refresh_functions(self, event: AstrMessageEvent):
        """刷新动态LLM函数"""
        try:
            self.dynamic_llm_manager.refresh_functions()
            registered_count = len(self.dynamic_llm_manager.get_registered_functions())
            yield event.plain_result(
                f"刷新完成，当前注册了 {registered_count} 个动态LLM函数"
            )
        except Exception as e:
            logger.error(f"刷新动态LLM函数失败: {e}")
            yield event.plain_result(f"刷新失败：{str(e)}")
