import os
import json
from typing import List, Dict, Optional


def is_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def default_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def chat_text(messages: List[Dict[str, str]], model: Optional[str] = None, max_tokens: int = 256) -> Optional[str]:
    if not is_available():
        return None
    try:
        from openai import OpenAI
    except Exception:
        return None
    client = OpenAI()
    try:
        resp = client.chat.completions.create(
            model=model or default_model(),
            messages=messages,
            temperature=0.2,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return None

