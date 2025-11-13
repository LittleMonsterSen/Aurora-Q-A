#!/usr/bin/env python3
"""
Ingest messages from the November 7 public API into mem0 Platform (MemoryClient),
adding one message at a time as a memory for the corresponding user_id.
Usage examples (run from repo root):
- Ingest everything:
  uv run --env-file .env python -m scripts.memory
- Ingest only one user:
  uv run --env-file .env python -m scripts.memory --user-id <UUID>
- Ingest first 500 messages to test:
  uv run --env-file .env python -m scripts.memory --max 500
Requires:
- MEM0_API_KEY in your environment (mem0 Platform key)
- OPENAI_API_KEY in env for mem0 embeddings (if your mem0 project uses OpenAI)
"""
import argparse
import asyncio
import os
import sys
import time
from typing import Any, Dict, List, Optional
import httpx
def _print(msg: str) -> None:
    try:
        print(msg, flush=True)
    except Exception:
        pass
async def fetch_all_messages(base: str, page_limit: int = 400, max_pages: int = 100, retries: int = 3) -> List[Dict[str, Any]]:
    base = base.rstrip("/")
    url = f"{base}/messages/"
    items: List[Dict[str, Any]] = []
    headers = {"Accept": "application/json", "User-Agent": "aurora-qa/ingest/1.0"}
    _print(f"Fetching messages from {url} (page_limit={page_limit}, max_pages={max_pages})")
    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        # discover total (best-effort)
        try:
            r = await client.get(url, params={"limit": 1})
            r.raise_for_status()
            total = int(r.json().get("total", 0))
        except Exception:
            total = 0
        pages = (total + page_limit - 1) // page_limit if total else max_pages
        pages = min(pages, max_pages)
        for i in range(pages):
            skip = i * page_limit
            attempt = 0
            while attempt < retries:
                attempt += 1
                resp = await client.get(url, params={"skip": skip, "limit": page_limit})
                if resp.status_code in (401, 403, 429, 500, 502, 503):
                    await asyncio.sleep(0.25 * attempt)
                    continue
                try:
                    resp.raise_for_status()
                except Exception as e:
                    _print(f"WARN: page skip={skip} failed: {e}")
                    break
                data = resp.json()
                batch = data.get("items", [])
                items.extend(batch)
                _print(f"Fetched page {i+1}/{pages} (+{len(batch)} items)")
                if len(batch) < page_limit:
                    return items
                break
    return items

def ingest_messages(messages: List[Dict[str, Any]], only_user: Optional[str] = None, max_items: Optional[int] = None, throttle_s: float = 0.0) -> None:
    try:
        from mem0 import MemoryClient  # type: ignore
    except Exception as e:
        _print(f"ERROR: mem0 platform client not available: {e}")
        sys.exit(2)
    api_key = os.getenv("MEM0_API_KEY")
    
    try:
        client = MemoryClient(api_key=api_key)
    except TypeError:
        client = MemoryClient()  # type: ignore
    total = 0
    added = 0
    skipped = 0
    for m in messages:
        if only_user and m.get("user_id") != only_user:
            continue
        total += 1
        text = (m.get("user_name")+" says "+m.get("message")+" at "+m.get("timestamp") or "").strip()
        if not text:
            skipped += 1
            continue
        meta = {
            "message_id": m.get("id"),
            "timestamp": m.get("timestamp"),
            "user_name": m.get("user_name"),
        }
        try:
            # Platform API generally accepts named 'text'
            client.add(text=text, user_id=m.get("user_id"), metadata=meta)  # type: ignore
            added += 1
        except TypeError:
            # Fallback positional for older variants
            client.add(text, user_id=m.get("user_id"), metadata=meta)  # type: ignore
            added += 1
        except Exception as e:
            _print(f"ERROR add failed for message {m.get('id')}: {e}")
        if throttle_s > 0:
            time.sleep(throttle_s)
        if max_items and added >= max_items:
            break
    _print(f"Ingest summary — considered: {total}, added: {added}, skipped(empty): {skipped}")

def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest messages into mem0 Platform one by one")
    parser.add_argument(
        "--base",
        default=os.getenv(
            "MESSAGES_API_BASE", "https://november7-730026606190.europe-west1.run.app"
        ),
        help="Base URL for the November 7 API",
    )
    parser.add_argument("--page-limit", type=int, default=200)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--user-id", type=str, default="", help="Only ingest this user_id")
    parser.add_argument("--max", type=int, default=0, help="Max items to add (0 = no cap)")
    parser.add_argument("--throttle", type=float, default=0.0, help="Sleep seconds between adds")
    args = parser.parse_args()
    messages = asyncio.run(
        fetch_all_messages(args.base, page_limit=args.page_limit, max_pages=args.max_pages)
    )
    only_user = args.user_id or None
    max_items = args.max if args.max and args.max > 0 else None
    ingest_messages(messages, only_user=only_user, max_items=max_items, throttle_s=args.throttle)
    return 0
if __name__ == "__main__":
    raise SystemExit(main())