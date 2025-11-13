#!/usr/bin/env python3
import argparse
import asyncio
import os
import sys
from typing import Dict, List
import httpx

# Ensure project root is importable when run as a script
THIS_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.name_index import build_names_index, save_names_index
from scripts.memory import fetch_all_messages

async def build_index(base: str) -> int:
    msgs = await fetch_all_messages(base)
    # pick latest user_name seen per user_id
    latest_name: Dict[str, str] = {}
    for m in msgs:
        uid = m.get("user_id")
        uname = m.get("user_name")
        if uid and uname:
            latest_name[uid] = uname
    users = [{"user_id": uid, "user_name": name} for uid, name in latest_name.items()]
    index = build_names_index(users)
    save_names_index(index)
    print(f"Built name index for {len(users)} users.")
    return len(users)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build local name→user_id index from the messages API")
    parser.add_argument(
        "--base",
        default=os.getenv(
            "MESSAGES_API_BASE", "https://november7-730026606190.europe-west1.run.app"
        ),
        help="Base URL for the November 7 API",
    )
    args = parser.parse_args()
    asyncio.run(build_index(args.base))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

