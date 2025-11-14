#!/usr/bin/env python3
"""
Ingest messages from the November 7 public API into mem0 Platform (MemoryClient),
grouping messages by user and date. All messages from the same day for a user are
combined into a single memory entry.

Usage examples (run from repo root):
- Ingest everything:
  uv run --env-file .env python -m scripts.memory
- Ingest only one user:
  uv run --env-file .env python -m scripts.memory --user-id <UUID>
- Ingest first 500 messages to test:
  uv run --env-file .env python -m scripts.memory --max 500

Memory format:
- Messages are grouped by (user_id, date)
- Each group becomes a single memory with all messages from that day
- Metadata includes only: date (YYYY-MM-DD) and user_name

Requires:
- MEM0_API_KEY in your environment (mem0 Platform key)
- OPENAI_API_KEY in env for mem0 embeddings (if your mem0 project uses OpenAI)
"""
import argparse
import asyncio
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
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

def extract_date(timestamp: str) -> Optional[str]:
    """Extract date (YYYY-MM-DD) from ISO timestamp string.
    
    Handles formats like:
    - "2025-08-02T05:20:44.159269+00:00"
    - "2025-08-02T05:20:44.159269Z"
    - "2025-08-02T05:20:44.159269"
    """
    if not timestamp:
        return None
    try:
        # Handle Z timezone format (replace Z with +00:00 for fromisoformat)
        ts_clean = timestamp.replace("Z", "+00:00")
        # fromisoformat handles: "2025-08-02T05:20:44.159269+00:00" directly
        dt = datetime.fromisoformat(ts_clean)
        return dt.date().isoformat()  # Returns YYYY-MM-DD
    except Exception as e:
        _print(f"WARN: Could not parse timestamp '{timestamp}': {e}")
        return None

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
    
    # Group messages by user_id and date
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    total = 0
    skipped_pre_group = 0
    
    for m in messages:
        if only_user and m.get("user_id") != only_user:
            continue
        total += 1
        message_content = (m.get("message") or "").strip()
        if not message_content:
            skipped_pre_group += 1
            continue
        
        user_id = m.get("user_id")
        timestamp = m.get("timestamp", "")
        date = extract_date(timestamp)
        
        if not user_id or not date:
            skipped_pre_group += 1
            continue
        
        # Group by (user_id, date)
        key = (user_id, date)
        grouped[key].append(m)
    
    _print(f"Grouped {total} messages into {len(grouped)} day-user groups (skipped {skipped_pre_group} empty/invalid)")
    
    added = 0
    skipped = 0
    
    # Process each group (user + date combination)
    for (user_id, date), day_messages in grouped.items():
        if max_items and added >= max_items:
            break
        
        # Sort messages by timestamp to maintain chronological order
        def get_timestamp_sort_key(m: Dict[str, Any]) -> float:
            """Extract timestamp as sortable float (seconds since epoch)."""
            ts = m.get("timestamp", "")
            if not ts:
                return 0.0
            try:
                ts_clean = ts.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts_clean)
                return dt.timestamp()
            except Exception:
                return 0.0
        
        day_messages_sorted = sorted(day_messages, key=get_timestamp_sort_key)
        
        # Get user_name from first message (should be same for all messages in group)
        user_name = day_messages_sorted[0].get("user_name", "User")
        
        # Format all messages from the same day into a single message list
        # Messages are in chronological order (sorted by timestamp)
        # See: https://docs.mem0.ai/core-concepts/memory-operations/add
        message_list = []
        for m in day_messages_sorted:
            message_content = (m.get("message") or "").strip()
            if message_content:
                message_list.append({
                    "role": "user",
                    "content": f"{message_content}"
                })
        
        if not message_list:
            skipped += 1
            continue
        
        # Metadata only includes date and user_name
        meta = {
            "date": date,
            "user_name": user_name,
        }
        
        # Retry logic for 502 and other transient errors
        max_retries = 3
        retry_delay = 1.0
        added_this_group = False
        
        for attempt in range(max_retries):
            try:
                # Use messages parameter as per mem0 API documentation
                client.add(messages=message_list, user_id=user_id, metadata=meta)  # type: ignore
                added += 1
                added_this_group = True
                _print(f"Added {len(message_list)} messages for {user_name} on {date}")
                break
            except Exception as e:
                error_str = str(e)
                # Check if it's a 502 or other retryable error
                if "502" in error_str or "503" in error_str or "504" in error_str or "429" in error_str:
                    if attempt < max_retries - 1:
                        _print(f"Retryable error for {user_name} on {date} (attempt {attempt + 1}/{max_retries}): {error_str}")
                        time.sleep(retry_delay * (attempt + 1))
                        continue
                _print(f"ERROR add failed for {user_name} on {date}: {e}")
                break
        
        if not added_this_group:
            skipped += 1
        
        if throttle_s > 0:
            time.sleep(throttle_s)
    
    _print(f"Ingest summary — considered: {total}, grouped: {len(grouped)}, added: {added}, skipped: {skipped + skipped_pre_group}")

def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest messages into mem0 Platform one by one")
    parser.add_argument(
        "--base",
        default=os.getenv(
            "MESSAGES_API_BASE", "https://november7-730026606190.europe-west1.run.app"
        ),
        help="Base URL for the November 7 API",
    )
    parser.add_argument("--page-limit", type=int, default=4000)
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