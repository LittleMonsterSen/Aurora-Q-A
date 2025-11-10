import os
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

import httpx

from .llm import chat_text, is_available as llm_available


def _strip_accents(s: str) -> str:
    return (
        unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
        if isinstance(s, str)
        else s
    )


def _norm_name(s: str) -> str:
    s = _strip_accents(s or "")
    s = s.lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


class MemoryAgent:
    """Thin wrapper around mem0 MemoryClient with per-user namespaces."""

    def __init__(self) -> None:
        try:
            from mem0 import MemoryClient  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "mem0 is required but not installed. Ensure it's in requirements and installed."
            ) from exc
        self._client = MemoryClient()

    def memorize(self, user_id: str, text: str, metadata: Optional[Dict] = None) -> None:
        if not text:
            return
        # Prefer new API add(); fall back to memorize() if unavailable
        if hasattr(self._client, "add"):
            self._client.add(text=text, user_id=user_id, metadata=metadata or {})  # type: ignore
        else:
            self._client.memorize(text, user_id=user_id, metadata=metadata or {})  # type: ignore

    def search(self, user_id: str, query: str, k: int = 12) -> List[Dict]:
        res = self._client.search(query=query, user_id=user_id)
        # mem0 returns a list of memory dicts; keep top-k if present
        if isinstance(res, list):
            return res[:k]
        return []


async def fetch_all_messages(base_url: str, limit: int = 200) -> List[Dict]:
    url = f"{base_url.rstrip('/')}/messages/"
    all_items: List[Dict] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        skip = 0
        while True:
            resp = await client.get(url, params={"skip": skip, "limit": limit})
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            if not items:
                break
            all_items.extend(items)
            if len(items) < limit:
                break
            skip += limit
    return all_items


def group_by_user(messages: List[Dict]) -> Dict[str, List[Dict]]:
    by_user: Dict[str, List[Dict]] = {}
    for m in messages:
        uid = m.get("user_id")
        by_user.setdefault(uid, []).append(m)
    for uid, msgs in by_user.items():
        msgs.sort(key=lambda x: x.get("timestamp", ""))
    return by_user


def latest_user_name(msgs: List[Dict]) -> str:
    for m in reversed(msgs):
        if m.get("user_name"):
            return m["user_name"]
    return ""


async def resolve_user_id(base_url: str, name_or_id: str) -> Optional[Tuple[str, str]]:
    # UUID-like → accept as-is
    if re.match(r"^[0-9a-fA-F-]{32,36}$", name_or_id):
        return name_or_id, ""
    # Otherwise, match by name
    messages = await fetch_all_messages(base_url, limit=300)
    query = _norm_name(name_or_id)
    best = None
    best_score = 0
    for m in messages:
        uid = m.get("user_id")
        uname_raw = m.get("user_name", "")
        uname = _norm_name(uname_raw)
        if not uid or not uname:
            continue
        score = 0
        if query and query in uname:
            score += 2
        q_first = query.split(" ")[0] if query else ""
        if q_first and re.search(rf"\b{re.escape(q_first)}\b", uname):
            score += 1
        if score > best_score:
            best_score = score
            best = (uid, uname_raw)
    return best


async def build_user_memory(agent: MemoryAgent, base_url: str, user_id: str) -> int:
    """Ingest messages for a single user into mem0. Returns count of ingested messages."""
    messages = await fetch_all_messages(base_url)
    user_msgs = [m for m in messages if m.get("user_id") == user_id]
    user_msgs.sort(key=lambda x: x.get("timestamp", ""))
    for m in user_msgs:
        text = m.get("message", "")
        meta = {"message_id": m.get("id"), "timestamp": m.get("timestamp"), "user_name": m.get("user_name")}
        agent.memorize(user_id=user_id, text=text, metadata=meta)
    return len(user_msgs)


async def answer_with_memory(agent: MemoryAgent, base_url: str, question: str, user_id: str) -> str:
    if not llm_available():
        return "OpenAI key missing. Set OPENAI_API_KEY."
    # Ensure memory exists (idempotent ingestion)
    await build_user_memory(agent, base_url, user_id)
    # Retrieve relevant memories then ask LLM to answer strictly from them
    memories = agent.search(user_id=user_id, query=question, k=12)
    if not memories:
        return "I don't know"
    # Combine memory items into a concise context
    snippets: List[str] = []
    for item in memories:
        # mem0 items often include 'memory' or 'text'
        txt = item.get("memory") or item.get("text") or item.get("content") or ""
        if txt:
            snippets.append(f"- {txt}")
    context = "\n".join(snippets[:12])
    system = (
        "You answer questions strictly using the provided memory snippets for a single person. "
        "If the answer is not present, reply exactly: I don't know. Be concise."
    )
    user = f"Memory snippets:\n{context}\n\nQuestion: {question}\nAnswer:"
    out = chat_text([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])
    return (out or "I don't know").strip()
