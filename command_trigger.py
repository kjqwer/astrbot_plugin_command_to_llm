import asyncio
from astrbot.api import logger
from astrbot.api.message_components import Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.message_event_result import MessageChain
from .event_factory import EventFactory


class CommandTrigger:
    """指令触发器，用于触发其他插件指令并捕获结果"""

    def __init__(self, context):
        self.context = context
        self.captured_messages = []  # 存储捕获到的消息
        self.original_send_method = None  # 保存原始的send方法
        self.target_event = None  # 目标事件对象
        self.event_factory = EventFactory(context)  # 事件工厂

    def setup_message_interceptor(self, target_event):
        """设置消息拦截器来捕获指令的响应"""
        self.target_event = target_event
        self.captured_messages = []

        # 保存原始的send方法
        if self.original_send_method is None:
            self.original_send_method = target_event.send

        # 创建拦截器包装函数
        async def intercepted_send(message_chain):
            # 捕获这条消息
            if message_chain is not None and hasattr(message_chain, "chain"):
                logger.info(
                    f"捕获到指令响应消息，包含 {len(message_chain.chain)} 个组件"
                )
                self.captured_messages.append(message_chain)
            else:
                logger.info(f"捕获到指令响应消息，但消息为空或格式不正确")
                # 即使消息为空，也记录为已捕获
                if message_chain is not None:
                    self.captured_messages.append(message_chain)

            # 设置已发送标记，但不实际发送到平台
            target_event._has_send_oper = True
            return True

        # 替换事件的send方法
        target_event.send = intercepted_send
        logger.info(f"已设置消息拦截器，监听事件: {target_event.unified_msg_origin}")

    def restore_message_sender(self):
        """恢复原始的消息发送器"""
        if self.original_send_method and self.target_event:
            self.target_event.send = self.original_send_method
            logger.info("已恢复原始消息发送器")

    def create_command_event(
        self,
        unified_msg_origin: str,
        command: str,
        creator_id: str,
        creator_name: str = None,
    ) -> AstrMessageEvent:
        """创建指令事件对象"""
        return self.event_factory.create_event(
            unified_msg_origin, command, creator_id, creator_name
        )

    async def trigger_and_capture_command(
        self,
        unified_msg_origin: str,
        command: str,
        creator_id: str,
        creator_name: str = None,
        max_wait_time: float = 20.0,
        wait_interval: float = 0.1,
    ):
        """触发指令并捕获响应"""
        try:
            logger.info(f"开始触发指令: {command}")

            # 创建指令事件
            fake_event = self.create_command_event(
                unified_msg_origin, command, creator_id, creator_name
            )

            # 设置消息拦截器
            self.setup_message_interceptor(fake_event)

            # 提交事件到事件队列
            event_queue = self.context.get_event_queue()
            event_queue.put_nowait(fake_event)

            logger.info(f"已将指令事件 {command} 提交到事件队列")

            # 等待指令执行并捕获响应
            max_wait_time = max(max_wait_time, 1.0)
            wait_interval = max(wait_interval, 0.05)
            waited_time = 0.0

            while waited_time < max_wait_time:
                await asyncio.sleep(wait_interval)
                waited_time += wait_interval

                # 检查是否捕获到了消息
                if self.captured_messages:
                    logger.info(f"成功捕获到 {len(self.captured_messages)} 条响应消息")
                    break

            # 恢复原始消息发送器
            self.restore_message_sender()

            if self.captured_messages:
                return True, self.captured_messages
            else:
                logger.warning(
                    f"等待 {max_wait_time} 秒后未捕获到指令 {command} 的响应消息"
                )
                return False, []

        except Exception as e:
            logger.error(f"触发指令失败: {str(e)}")
            import traceback

            logger.error(traceback.format_exc())

            # 确保恢复原始消息发送器
            self.restore_message_sender()
            return False, []

    async def trigger_and_forward_command(
        self,
        unified_msg_origin: str,
        command: str,
        creator_id: str,
        creator_name: str = None,
        max_wait_time: float = 20.0,
        wait_interval: float = 0.1,
        forward_interval: float = 0.5,
    ):
        """触发指令并转发结果"""
        # 触发指令并捕获响应
        success, captured_messages = await self.trigger_and_capture_command(
            unified_msg_origin,
            command,
            creator_id,
            creator_name,
            max_wait_time,
            wait_interval,
        )

        if success and captured_messages:
            logger.info(
                f"成功捕获到指令 {command} 的 {len(captured_messages)} 条响应，开始转发"
            )

            # 转发捕获到的消息
            for i, captured_msg in enumerate(captured_messages):
                logger.info(
                    f"转发第 {i + 1} 条消息，包含 {len(captured_msg.chain)} 个组件"
                )

                # 发送捕获到的消息
                await self.context.send_message(unified_msg_origin, captured_msg)

                # 如果有多条消息，添加间隔
                if len(captured_messages) > 1 and i < len(captured_messages) - 1:
                    await asyncio.sleep(max(forward_interval, 0.0))
        else:
            logger.warning(f"未能捕获到指令 {command} 的响应")

            # 发送执行失败的提示
            error_msg = MessageChain()
            error_msg.chain.append(Plain(f"指令 {command} 执行失败，未收到响应"))

            await self.context.send_message(unified_msg_origin, error_msg)
