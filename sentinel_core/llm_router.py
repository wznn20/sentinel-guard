"""
Sentinel LLM Router — 多模型路由，支持100+提供商
"""
import logging
from typing import Optional, AsyncIterator
from pydantic import BaseModel

logger = logging.getLogger("sentinel.llm")


class ModelConfig(BaseModel):
    provider: str = "openrouter"
    model: str = "anthropic/claude-sonnet-4"
    api_key: str = ""
    base_url: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 4096


class LLMRouter:
    """LLM路由 — 统一接口，支持任意提供商"""

    def __init__(self, config):
        self.primary = ModelConfig(
            provider=getattr(config, 'provider', 'openrouter'),
            model=getattr(config, 'model', 'anthropic/claude-sonnet-4'),
            api_key=getattr(config, 'api_key', ''),
        )
        self._initialized = False

    async def initialize(self):
        """验证LLM连接"""
        try:
            import litellm
            litellm.suppress_debug_info = True
            self._initialized = True
            logger.info(f"✅ LLM Router initialized: {self.primary.provider}/{self.primary.model}")
        except ImportError:
            logger.error("❌ litellm not installed. Run: pip install litellm")
            raise

    async def chat(self, messages: list, stream: bool = False) -> str:
        """发送对话请求"""
        if not self._initialized:
            await self.initialize()

        import litellm

        try:
            response = await litellm.acompletion(
                model=f"{self.primary.provider}/{self.primary.model}",
                messages=messages,
                api_key=self.primary.api_key,
                temperature=self.primary.temperature,
                max_tokens=self.primary.max_tokens,
                stream=stream,
            )
            if stream:
                return response
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return f"⚠️ AI分析暂时不可用: {str(e)}"

    async def classify(self, text: str, categories: list[str]) -> str:
        """快速分类（用于告警分级等）"""
        messages = [
            {"role": "system", "content": "你是安全分析助手。只回复分类标签，不要解释。"},
            {"role": "user", "content": f"将以下内容分类为: {', '.join(categories)}\n\n{text}"}
        ]
        result = await self.chat(messages)
        return result.strip()
