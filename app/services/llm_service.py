import logging

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# DeepSeek 兼容 OpenAI 接口
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        logger.info("Initializing DeepSeek client (base_url=%s)", settings.deepseek_base_url)
        _client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
    return _client


def chat(prompt: str, model: str = "deepseek-chat") -> str:
    client = _get_client()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        logger.exception("DeepSeek API call failed")
        raise
    if not resp.choices:
        logger.warning("DeepSeek returned empty choices")
        return ""
    return resp.choices[0].message.content or ""
