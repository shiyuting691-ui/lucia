"""
OpenAI-Compatible Provider — 支持 DeepSeek / Qwen / 其他兼容接口

环境变量：
  DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
  QWEN_API_KEY,     QWEN_BASE_URL,     QWEN_MODEL
"""
import os
import json
import time
import logging
import re
import requests

from .base import BaseLLMProvider, LLMResponse

logger = logging.getLogger(__name__)

TIMEOUT = int(os.environ.get("LLM_TIMEOUT_SECONDS", "60"))

# DeepSeek 默认配置
DEEPSEEK_DEFAULTS = {
    "base_url": "https://api.deepseek.com",
    "model":    "deepseek-chat",
}

# Qwen 默认配置（阿里云）
QWEN_DEFAULTS = {
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model":    "qwen-turbo",
}


class OpenAICompatibleProvider(BaseLLMProvider):
    """
    单个 OpenAI-Compatible 端点的 Provider。
    通过 provider_name 参数区分 deepseek / qwen / 其他。
    """

    def __init__(self, provider_name: str = "deepseek"):
        self.provider_name = provider_name
        prefix = provider_name.upper()

        self._api_key  = os.environ.get(f"{prefix}_API_KEY", "")
        self._base_url = os.environ.get(f"{prefix}_BASE_URL", "")
        self._model    = os.environ.get(f"{prefix}_MODEL", "")

        # 填入默认值
        if provider_name == "deepseek":
            self._base_url = self._base_url or DEEPSEEK_DEFAULTS["base_url"]
            self._model    = self._model    or DEEPSEEK_DEFAULTS["model"]
        elif provider_name == "qwen":
            self._base_url = self._base_url or QWEN_DEFAULTS["base_url"]
            self._model    = self._model    or QWEN_DEFAULTS["model"]

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def health_check(self) -> dict:
        if not self.is_configured():
            return {"status": "not_configured", "available": False,
                    "provider": self.provider_name}
        try:
            resp = self.generate_text("说'ok'", max_tokens=10)
            if resp.success:
                return {"status": "success", "available": True,
                        "provider": self.provider_name, "model": self._model}
            return {"status": "failed", "available": False,
                    "provider": self.provider_name, "error": resp.error}
        except Exception as e:
            return {"status": "failed", "available": False,
                    "provider": self.provider_name, "error": str(e)}

    def generate_text(self, prompt: str, system_prompt=None,
                      temperature: float = 0.2, max_tokens: int = 2000) -> LLMResponse:
        if not self.is_configured():
            return LLMResponse(success=False, provider=self.provider_name,
                               error="provider_not_configured")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        t0 = time.time()
        try:
            r = requests.post(
                f"{self._base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model":       self._model,
                    "messages":    messages,
                    "temperature": temperature,
                    "max_tokens":  max_tokens,
                },
                timeout=TIMEOUT,
            )
            latency = int((time.time() - t0) * 1000)

            if r.status_code != 200:
                err = f"HTTP {r.status_code}: {r.text[:200]}"
                logger.warning(f"[{self.provider_name}] {err}")
                return LLMResponse(success=False, provider=self.provider_name,
                                   model=self._model, error=err, latency_ms=latency)

            data    = r.json()
            content = data["choices"][0]["message"]["content"]
            usage   = data.get("usage", {})
            logger.info(f"[{self.provider_name}] generate_text OK latency={latency}ms "
                        f"tokens={usage.get('total_tokens', '?')}")
            return LLMResponse(
                success=True, content=content, provider=self.provider_name,
                model=self._model, latency_ms=latency,
                token_usage={"prompt": usage.get("prompt_tokens", 0),
                             "completion": usage.get("completion_tokens", 0),
                             "total": usage.get("total_tokens", 0)},
            )
        except requests.Timeout:
            latency = int((time.time() - t0) * 1000)
            logger.warning(f"[{self.provider_name}] timeout after {latency}ms")
            return LLMResponse(success=False, provider=self.provider_name,
                               model=self._model, error="timeout", latency_ms=latency)
        except Exception as e:
            latency = int((time.time() - t0) * 1000)
            logger.error(f"[{self.provider_name}] error: {e}")
            return LLMResponse(success=False, provider=self.provider_name,
                               model=self._model, error=str(e), latency_ms=latency)

    def generate_json(self, prompt: str, system_prompt=None,
                      temperature: float = 0.1, max_tokens: int = 2000) -> LLMResponse:
        """调用 generate_text 并从输出中提取 JSON"""
        json_hint = "\n\n请严格以合法 JSON 格式输出，不要包含任何其他说明文字。"
        resp = self.generate_text(
            prompt + json_hint,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if not resp.success:
            return resp

        raw = resp.content or ""
        parsed = _extract_json(raw)
        if parsed is None:
            return LLMResponse(success=False, provider=self.provider_name,
                               model=self._model, error="invalid_json",
                               content=raw, latency_ms=resp.latency_ms)

        resp.json_data = parsed
        return resp


def _extract_json(text: str):
    """从文本中提取第一个合法 JSON 对象/数组"""
    # 去掉 ```json ... ``` 包裹
    text = re.sub(r"```(?:json)?", "", text).strip()
    # 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 找到第一个 { 或 [
    for start_ch, end_ch in [('{', '}'), ('[', ']')]:
        idx = text.find(start_ch)
        if idx == -1:
            continue
        depth = 0
        for i, ch in enumerate(text[idx:], idx):
            if ch == start_ch:
                depth += 1
            elif ch == end_ch:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[idx:i + 1])
                    except json.JSONDecodeError:
                        break
    return None
