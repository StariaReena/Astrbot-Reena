import asyncio


from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import ResultContentType, MessageChain

from astrbot.core.provider.entites import ProviderRequest, LLMResponse


@register("TokenCalculator", "rinen0721", "计算并显示Token消耗的插件，部分provider可用", "1.0.0", "https://github.com/rinen0721/astrbot_plugin_token_calculator")
class TokenCalculator(Star):
    cacuToken:bool =True
    debugMode:bool =False #用于开启或关闭调试日志
    tokenMsg:str =""
    llmResponsed:bool=False #通过这个变量确定是llm请求之后的消息而不是指令



    def __init__(self, context: Context):
        super().__init__(context)

    # 注册指令的装饰器。指令名为 CacuToken。注册成功后，发送 `/CacuToken` 就会触发这个指令，并开启/关闭计算Token的功能
    @filter.command("CacuToken")
    async def CacuToken(self, event: AstrMessageEvent):
        """输入/CacuToken以开启/关闭Token计算"""  # 这是 handler 的描述，将会被解析方便用户了解插件内容。建议填写。
        self.cacuToken=not self.cacuToken
        if self.cacuToken:
            yield event.plain_result(f"开启计算Token功能") # 发送一条纯文本消息
        else:
            yield event.plain_result(f"关闭计算Token功能")  # 发送一条纯文本消息

    # 注册指令的装饰器。指令名为 TokenCalcDebug。注册成功后，发送 `/TokenCalcDebug` 就会触发这个指令，并开启/关闭调试日志功能
    @filter.command("TokenCalcDebug")
    async def TokenCalcDebug(self, event: AstrMessageEvent):
        """输入/TokenCalcDebug以开启/关闭Token调试日志"""
        self.debugMode = not self.debugMode
        if self.debugMode:
            yield event.plain_result(f"开启Token调试日志功能")
        else:
            yield event.plain_result(f"关闭Token调试日志功能")


    @filter.on_llm_response()
    async def on_llm_resp(self, event: AstrMessageEvent, resp: LLMResponse):
        if not self.cacuToken:
            return
            
        if self.debugMode:
            logger.info(f"[TokenCalculator] on_llm_response triggered.")

        try:
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            
            # 优先从 AstrBot 核心的 usage 对象获取
            if resp.usage:
                prompt_tokens = resp.usage.input
                completion_tokens = resp.usage.output
                total_tokens = resp.usage.total
                if self.debugMode:
                    logger.info(f"[TokenCalculator] 从 resp.usage 获取到 Token: {total_tokens}")

            # 备选：从原始响应中获取 (OpenAI 兼容型)
            elif resp.raw_completion and hasattr(resp.raw_completion, "usage") and resp.raw_completion.usage:
                usage = resp.raw_completion.usage
                prompt_tokens = getattr(usage, "prompt_tokens", 0)
                completion_tokens = getattr(usage, "completion_tokens", 0)
                total_tokens = getattr(usage, "total_tokens", 0)
                if self.debugMode:
                    logger.info(f"[TokenCalculator] 从 raw_completion 获取到 Token: {total_tokens}")

            if total_tokens > 0:
                self.tokenMsg = f"(completion_tokens:{completion_tokens}, prompt_tokens:{prompt_tokens}, token总消耗:{total_tokens})"
            else:
                if self.debugMode:
                    logger.info(f"[TokenCalculator] 未在响应中找到有效的 Token 使用信息。")
                self.tokenMsg = "(无法获取Token用量信息，可能是当前provider不支持)"

            self.llmResponsed = True
            if self.debugMode:
                logger.info(f"[TokenCalculator] 已记录 Token 信息，等待后续处理。")

        except Exception as e:
            logger.error(f"[TokenCalculator] 出现错误: {e}", exc_info=True)
            self.tokenMsg = "(TokenCalculator插件内部错误)"


    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        if not (self.cacuToken and self.llmResponsed):
            return
            
        if self.debugMode:
            logger.info(f"[TokenCalculator] on_decorating_result triggered. 准备处理 Token 信息")
            
        try:
            result = event.get_result()
            res_type = result.result_content_type if result else "None"
            
            if result and result.result_content_type == ResultContentType.STREAMING_FINISH:
                if self.debugMode:
                    logger.info(f"[TokenCalculator] 检测到流式结束 (STREAMING_FINISH)，等待 2s 后发送 Token 信息。")
                await asyncio.sleep(2)
                await event.send(MessageChain([Plain(self.tokenMsg)]))
                self.llmResponsed = False
                
            elif result and result.result_content_type == ResultContentType.LLM_RESULT:
                if self.debugMode:
                    logger.info(f"[TokenCalculator] 非流式模式 (LLM_RESULT)，将 Token 信息追加到 chain 末尾。")
                chain = result.chain
                chain.append(Plain(self.tokenMsg))
                self.llmResponsed = False
                
        except Exception as e:
            logger.error(f"[TokenCalculator] Error in on_decorating_result: {e}")
            raise RuntimeError("CacuToken插件在回复消息的时候出现错误")
