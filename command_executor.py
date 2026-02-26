import asyncio
from typing import List, Tuple
from astrbot.api import logger
from astrbot.core.message.message_event_result import MessageChain
from .command_trigger import CommandTrigger


class CommandExecutor:
    """指令执行器，使用CommandTrigger来执行指令并捕获结果"""

    def __init__(self, context):
        self.context = context
        self.command_trigger = CommandTrigger(context)

    async def execute_command(
        self,
        unified_msg_origin: str,
        command: str,
        creator_id: str,
        creator_name: str = None,
    ) -> Tuple[bool, List[MessageChain]]:
        """执行指令并捕获响应"""
        try:
            logger.info(f"开始执行指令: {command}")

            # 使用CommandTrigger来触发指令并捕获响应
            (
                success,
                captured_messages,
            ) = await self.command_trigger.trigger_and_capture_command(
                unified_msg_origin, command, creator_id, creator_name
            )

            if success:
                logger.info(
                    f"成功执行指令 {command}，捕获到 {len(captured_messages)} 条响应"
                )
                return True, captured_messages
            else:
                logger.warning(f"指令 {command} 执行失败，未捕获到响应")
                return False, []

        except Exception as e:
            logger.error(f"执行指令失败: {str(e)}")
            import traceback

            logger.error(traceback.format_exc())
            return False, []

    async def execute_command_with_options(
        self,
        unified_msg_origin: str,
        command: str,
        creator_id: str,
        creator_name: str = None,
        capture_timeout: float = 20.0,
        wait_interval: float = 0.1,
    ) -> Tuple[bool, List[MessageChain]]:
        """执行指令并捕获响应（可配置超时）"""
        try:
            logger.info(
                f"开始执行指令(可配置): {command}, capture_timeout={capture_timeout}, wait_interval={wait_interval}"
            )

            (
                success,
                captured_messages,
            ) = await self.command_trigger.trigger_and_capture_command(
                unified_msg_origin,
                command,
                creator_id,
                creator_name,
                max_wait_time=capture_timeout,
                wait_interval=wait_interval,
            )

            if success:
                logger.info(
                    f"成功执行指令 {command}，捕获到 {len(captured_messages)} 条响应"
                )
                return True, captured_messages

            logger.warning(f"指令 {command} 执行失败，未捕获到响应")
            return False, []
        except Exception as e:
            logger.error(f"执行指令失败(可配置): {str(e)}")
            import traceback

            logger.error(traceback.format_exc())
            return False, []

    async def execute_and_forward(
        self,
        unified_msg_origin: str,
        command: str,
        creator_id: str,
        creator_name: str = None,
    ):
        """执行指令并转发结果"""
        try:
            logger.info(f"开始执行并转发指令: {command}")

            # 使用CommandTrigger来触发指令并转发结果
            await self.command_trigger.trigger_and_forward_command(
                unified_msg_origin, command, creator_id, creator_name
            )

        except Exception as e:
            logger.error(f"执行并转发指令失败: {str(e)}")
            import traceback

            logger.error(traceback.format_exc())

    async def execute_and_forward_with_options(
        self,
        unified_msg_origin: str,
        command: str,
        creator_id: str,
        creator_name: str = None,
        capture_timeout: float = 20.0,
        wait_interval: float = 0.1,
        forward_interval: float = 0.5,
    ):
        """执行指令并转发结果（可配置超时与间隔）"""
        try:
            logger.info(
                f"开始执行并转发指令(可配置): {command}, capture_timeout={capture_timeout}, forward_interval={forward_interval}"
            )

            await self.command_trigger.trigger_and_forward_command(
                unified_msg_origin,
                command,
                creator_id,
                creator_name,
                max_wait_time=capture_timeout,
                wait_interval=wait_interval,
                forward_interval=forward_interval,
            )
        except Exception as e:
            logger.error(f"执行并转发指令失败(可配置): {str(e)}")
            import traceback

            logger.error(traceback.format_exc())
