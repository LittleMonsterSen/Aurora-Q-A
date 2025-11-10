#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx
from dateutil import parser as date_parser


def _strip_accents(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


def _norm(s: str) -> str:
    s = _strip_accents(s or "").lower()
    return " ".join("".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in s).split())


def fetch_all_messages(base: str, page_limit: int = 200, max_pages: int = 100, retries: int = 3) -> List[Dict[str, Any]]:
    base = base.rstrip("/")
    url = f"{base}/messages/"
    items: List[Dict[str, Any]] = []
    headers = {"Accept": "application/json", "User-Agent": "explorer/1.0"}
    with httpx.Client(timeout=30.0, headers=headers) as client:
        r = client.get(url, params={"limit": 1})
        r.raise_for_status()
        total = r.json().get("total", 0)
        if not isinstance(total, int) or total <= 0:
            total = page_limit * max_pages
        pages = min((total + page_limit - 1) // page_limit, max_pages)
        for i in range(pages):
            skip = i * page_limit
            attempt = 0
            while attempt < retries:
                attempt += 1
                try:
                    resp = client.get(url, params={"skip": skip, "limit": page_limit})
                    resp.raise_for_status()
                    data = resp.json()
                    batch = data.get("items", [])
                    items.extend(batch)
                    if len(batch) < page_limit:
                        return items
                    break
                except Exception:
                    if attempt >= retries:
                        raise
                    time.sleep(0.2 * attempt)
    return items


def group_by_user(messages: List[Dict[str, Any]]):
    by_user: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for m in messages:
        by_user[m.get("user_id", "")].append(m)
    for uid, arr in by_user.items():
        arr.sort(key=lambda x: x.get("timestamp", ""))
    return by_user


def luhn_check(num: str) -> bool:
    digits = [int(c) for c in num if c.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    parity = (len(digits) - 2) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def analyze(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_user = group_by_user(messages)

    # Name inconsistencies: same user_id seen with multiple names
    uid_to_names: Dict[str, List[str]] = {
        uid: sorted({m.get("user_name", "") for m in arr if m.get("user_name")}) for uid, arr in by_user.items()
    }
    multi_name_users = [
        {"user_id": uid, "names": names} for uid, names in uid_to_names.items() if len(names) > 1
    ]

    # Name collisions across users
    full_name_to_uids: Dict[str, set] = defaultdict(set)
    first_name_to_uids: Dict[str, set] = defaultdict(set)
    for m in messages:
        uname = m.get("user_name", "")
        uid = m.get("user_id", "")
        if uname:
            full_name_to_uids[uname].add(uid)
            first = _norm(uname).split(" ")[0] if _norm(uname) else ""
            if first:
                first_name_to_uids[first].add(uid)
    full_collisions = [
        {"user_name": n, "user_ids": sorted(list(uids))}
        for n, uids in full_name_to_uids.items() if len(uids) > 1
    ]
    first_collisions = [
        {"first": n, "user_count": len(uids)} for n, uids in first_name_to_uids.items() if len(uids) > 1
    ]
    first_collisions.sort(key=lambda x: x["user_count"], reverse=True)

    # Encoding anomalies (replacement char)
    bad_name_examples = sorted({m.get("user_name", "") for m in messages if "�" in (m.get("user_name", ""))})
    bad_message_samples = []
    for m in messages:
        t = m.get("message", "")
        if "�" in t:
            bad_message_samples.append({
                "id": m.get("id"),
                "user_id": m.get("user_id"),
                "user_name": m.get("user_name"),
                "snippet": t[:160],
            })
            if len(bad_message_samples) >= 50:
                break

    # Timestamp anomalies
    now = datetime.now(timezone.utc)
    far_future = now + timedelta(days=365)
    unparsable = 0
    future = 0
    far_past = 0
    out_of_order_users = 0
    for uid, arr in by_user.items():
        last_dt: Optional[datetime] = None
        out_of_order = False
        for m in arr:
            ts = m.get("timestamp", "")
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except Exception:
                unparsable += 1
                continue
            if dt > far_future:
                future += 1
            if dt.year < 2010:
                far_past += 1
            if last_dt and dt < last_dt:
                out_of_order = True
            last_dt = dt
        if out_of_order:
            out_of_order_users += 1

    # Duplicates per user and across users
    def norm_text(s: str) -> str:
        return " ".join((s or "").lower().split())

    per_user_duplicates: List[Dict[str, Any]] = []
    for uid, arr in by_user.items():
        counts: Dict[str, int] = {}
        for m in arr:
            key = norm_text(m.get("message", ""))
            counts[key] = counts.get(key, 0) + 1
        dups = [{"text": t, "count": c} for t, c in counts.items() if c > 1]
        if dups:
            per_user_duplicates.append({"user_id": uid, "examples": sorted(dups, key=lambda x: x["count"], reverse=True)[:5]})

    text_to_uids: Dict[str, set] = defaultdict(set)
    for m in messages:
        text_to_uids[norm_text(m.get("message", ""))].add(m.get("user_id", ""))
    cross_user_duplicate_texts = [
        {"text": t, "user_count": len(uids)} for t, uids in text_to_uids.items() if len(uids) > 1 and len(t) > 0
    ]
    cross_user_duplicate_texts.sort(key=lambda x: x["user_count"], reverse=True)
    cross_user_duplicate_texts = cross_user_duplicate_texts[:20]

    # PII samples
    import re as _re
    phone_re = _re.compile(r"\b(?:\+?\d[\d\s\-()]{7,}\d)\b")
    email_re = _re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    cc_re = _re.compile(r"(?:\d[ -]?){13,19}")
    phone_msgs = []
    email_msgs = []
    cc_msgs = []
    for m in messages:
        txt = m.get("message", "")
        if phone_re.search(txt):
            phone_msgs.append({"id": m.get("id"), "user_id": m.get("user_id"), "snippet": txt[:160]})
        if email_re.search(txt):
            email_msgs.append({"id": m.get("id"), "user_id": m.get("user_id"), "snippet": txt[:160]})
        for match in cc_re.finditer(txt):
            digits = "".join(ch for ch in match.group(0) if ch.isdigit())
            if 13 <= len(digits) <= 19 and luhn_check(digits):
                cc_msgs.append({"id": m.get("id"), "user_id": m.get("user_id"), "snippet": txt[:160]})
                break
        if len(phone_msgs) >= 10 and len(email_msgs) >= 10 and len(cc_msgs) >= 5:
            continue

    # Message stats and top words
    lengths = [len(m.get("message", "")) for m in messages]
    avg_len = round(sum(lengths) / max(1, len(lengths)), 2)
    min_len = min(lengths) if lengths else 0
    max_len = max(lengths) if lengths else 0
    stop = set(
        "a an the is are was were am i you he she it we they of to in on for with and or as at by from that this these those what when how many does do did have has had my me your our their".split()
    )
    word_counts: Counter[str] = Counter()
    for m in messages:
        for w in _norm(m.get("message", "")).split():
            if w and w not in stop:
                word_counts[w] += 1
    top_words = word_counts.most_common(25)

    # ID integrity and missing fields
    uuid_re = re.compile(r"^[0-9a-fA-F-]{32,36}$")
    invalid_user_ids = [m.get("user_id") for m in messages if not uuid_re.match(str(m.get("user_id", "")))]
    invalid_message_ids = [m.get("id") for m in messages if not uuid_re.match(str(m.get("id", "")))]
    missing_fields = {
        "missing_user_id": sum(1 for m in messages if not m.get("user_id")),
        "missing_user_name": sum(1 for m in messages if not m.get("user_name")),
        "missing_timestamp": sum(1 for m in messages if not m.get("timestamp")),
        "missing_message": sum(1 for m in messages if not m.get("message")),
    }

    # Duplicate message IDs
    id_counts: Dict[str, int] = {}
    for m in messages:
        mid = str(m.get("id"))
        id_counts[mid] = id_counts.get(mid, 0) + 1
    dup_ids = [mid for mid, c in id_counts.items() if c > 1]

    # Cross-user PII reuse (phones, emails)
    phone_re = re.compile(r"\b(?:\+?\d[\d\s\-()]{7,}\d)\b")
    email_re = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    def norm_phone(s: str) -> str:
        return re.sub(r"\D+", "", s)
    phone_to_users: Dict[str, set] = defaultdict(set)
    email_to_users: Dict[str, set] = defaultdict(set)
    for m in messages:
        txt = m.get("message", "") or ""
        uid = m.get("user_id", "")
        for ph in phone_re.findall(txt):
            phone_to_users[norm_phone(ph)].add(uid)
        for em in email_re.findall(txt):
            email_to_users[em.lower()].add(uid)
    shared_phones = [
        {"phone": p, "user_count": len(uids)} for p, uids in phone_to_users.items() if len(uids) > 1 and len(p) >= 7
    ]
    shared_emails = [
        {"email": e, "user_count": len(uids)} for e, uids in email_to_users.items() if len(uids) > 1
    ]
    shared_phones.sort(key=lambda x: x["user_count"], reverse=True)
    shared_emails.sort(key=lambda x: x["user_count"], reverse=True)

    # Preference flips (aisle vs window) and same-day multi-destinations
    city_list = {
        "new york", "nyc", "paris", "london", "tokyo", "milan", "monaco", "bangkok", "singapore",
        "rome", "berlin", "barcelona", "dubai", "sydney", "los angeles", "san francisco", "serengeti",
        "monte carlo", "venice", "prague", "vienna", "amsterdam", "seoul", "hong kong"
    }

    def extract_cities(text: str) -> List[str]:
        t = _norm(text)
        hits: List[str] = []
        for c in city_list:
            if c in t:
                hits.append(c)
        return hits

    date_patterns = [
        re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
        re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
        re.compile(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{4})?\b", re.IGNORECASE),
    ]
    def extract_dates(text: str) -> List[str]:
        found: List[str] = []
        for rx in date_patterns:
            for m in rx.findall(text):
                piece = m if isinstance(m, str) else (m[0] if isinstance(m, tuple) else "")
                piece = piece or (m if isinstance(m, str) else "")
                if not piece:
                    continue
                try:
                    dt = date_parser.parse(piece, fuzzy=True)
                    found.append(dt.date().isoformat())
                except Exception:
                    continue
        return list(dict.fromkeys(found))

    contradictions: List[Dict[str, Any]] = []
    same_day_multi_city: List[Dict[str, Any]] = []
    for uid, arr in by_user.items():
        pref_aisle = False
        pref_window = False
        date_to_cities: Dict[str, set] = defaultdict(set)
        for m in arr:
            txt = (m.get("message", "") or "").lower()
            if "prefer aisle" in txt:
                pref_aisle = True
            if "prefer window" in txt:
                pref_window = True
            dts = extract_dates(txt)
            if dts:
                cities = extract_cities(txt)
                for d in dts:
                    for c in cities:
                        date_to_cities[d].add(c)
        if pref_aisle and pref_window:
            contradictions.append({"user_id": uid, "type": "seat_preference_flip"})
        for d, cities in date_to_cities.items():
            if len(cities) > 1:
                same_day_multi_city.append({"user_id": uid, "date": d, "cities": sorted(list(cities))})

    # Cadence: burstiness / bot-like uniform intervals
    suspicious_cadence: List[Dict[str, Any]] = []
    for uid, arr in by_user.items():
        if len(arr) < 8:
            continue
        times: List[datetime] = []
        for m in arr:
            ts = m.get("timestamp", "")
            try:
                times.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
            except Exception:
                pass
        if len(times) < 8:
            continue
        times.sort()
        gaps = [(times[i] - times[i-1]).total_seconds() for i in range(1, len(times))]
        if not gaps:
            continue
        mean_gap = sum(gaps) / len(gaps)
        variance = sum((g - mean_gap) ** 2 for g in gaps) / len(gaps)
        std_gap = variance ** 0.5
        cv = std_gap / mean_gap if mean_gap > 0 else 0.0
        # suspicious if very regular and not enormous delays
        if 10.0 <= mean_gap <= 86400.0 and cv < 0.08:
            suspicious_cadence.append({"user_id": uid, "mean_gap_s": round(mean_gap, 1), "cv": round(cv, 4), "samples": len(gaps)})
    suspicious_cadence.sort(key=lambda x: x["cv"])

    # Language/script shift (very rough): ASCII ratio extremes across timeline
    lang_shifts: List[Dict[str, Any]] = []
    for uid, arr in by_user.items():
        ratios: List[float] = []
        for m in arr:
            t = (m.get("message", "") or "")
            if not t:
                continue
            ascii_chars = sum(1 for ch in t if ord(ch) < 128)
            ratio = ascii_chars / max(1, len(t))
            ratios.append(ratio)
        if not ratios:
            continue
        if min(ratios) < 0.6 and max(ratios) > 0.95:
            lang_shifts.append({"user_id": uid, "min_ascii_ratio": round(min(ratios), 3), "max_ascii_ratio": round(max(ratios), 3)})

    return {
        "totals": {
            "messages": len(messages),
            "users": len(by_user),
            "avg_message_length": avg_len,
            "min_message_length": min_len,
            "max_message_length": max_len,
        },
        "names": {
            "user_ids_with_multiple_names_count": len(multi_name_users),
            "user_ids_with_multiple_names_examples": multi_name_users[:10],
            "full_name_collisions_count": len(full_collisions),
            "full_name_collisions_examples": full_collisions[:10],
            "first_name_collisions_top": first_collisions[:20],
        },
        "encoding": {
            "names_with_replacement_char_count": len(bad_name_examples),
            "names_with_replacement_char_examples": bad_name_examples[:10],
            "sample_bad_messages": bad_message_samples,
        },
        "timestamps": {
            "unparsable": unparsable,
            "far_future_gt_1y": future,
            "far_past_lt_2010": far_past,
            "out_of_order_user_count": out_of_order_users,
        },
        "duplicates": {
            "per_user_duplicates_examples": per_user_duplicates[:10],
            "cross_user_duplicate_texts": cross_user_duplicate_texts,
            "duplicate_message_id_count": len(dup_ids),
            "duplicate_message_id_examples": dup_ids[:20],
        },
        "pii_samples": {
            "phone_like": phone_msgs[:10],
            "email_like": email_msgs[:10],
            "credit_card_like": cc_msgs[:5],
        },
        "top_words": top_words,
        "integrity": {
            "invalid_user_id_count": len(invalid_user_ids),
            "invalid_message_id_count": len(invalid_message_ids),
            "missing_fields": missing_fields,
        },
        "pii_cross_user_reuse": {
            "shared_phones": shared_phones[:20],
            "shared_emails": shared_emails[:20],
        },
        "contradictions": {
            "seat_preference_flips": contradictions[:50],
            "same_day_multi_city": same_day_multi_city[:50],
        },
        "cadence": {
            "suspicious_cadence_users": suspicious_cadence[:50],
        },
        "language": {
            "script_shift_users": lang_shifts[:50],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Explore and analyze messages grouped by user")
    parser.add_argument(
        "--base",
        default=os.getenv(
            "MESSAGES_API_BASE", "https://november7-730026606190.europe-west1.run.app"
        ),
        help="Base URL for the November 7 API",
    )
    parser.add_argument("--page-limit", type=int, default=200)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--output", type=str, default="", help="Write JSON report to this file")
    args = parser.parse_args()

    try:
        messages = fetch_all_messages(args.base, page_limit=args.page_limit, max_pages=args.max_pages)
    except Exception as e:
        print(f"Failed to fetch messages: {e}", file=sys.stderr)
        return 1

    report = analyze(messages)
    out = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"Wrote report to {args.output}")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
