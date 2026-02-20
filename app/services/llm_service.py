import logging

from openai import OpenAI

from app.config import settings
from app.prompts import PHISHING_JUDGE_SYSTEM, build_target_context

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


def chat(prompt: str, model: str = "deepseek-chat", target_info: dict | None = None) -> str:
    client = _get_client()
    system_content = PHISHING_JUDGE_SYSTEM
    if target_info:
        system_content += build_target_context(target_info)
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": prompt},
    ]
    logger.info("LLM request payload:\n[system] %s\n[user] %s", system_content, prompt)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
        )
    except Exception:
        logger.exception("DeepSeek API call failed")
        raise
    if not resp.choices:
        logger.warning("DeepSeek returned empty choices")
        return ""
    return resp.choices[0].message.content or ""
