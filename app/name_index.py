import json
import os
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

DATA_DIR = os.getenv("DATA_DIR", "data")
INDEX_DIR = os.path.join(DATA_DIR, "index")
NAMES_INDEX_FILE = os.path.join(INDEX_DIR, "names.json")


def _strip_accents(s: str) -> str:
    return (
        unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
        if isinstance(s, str)
        else s
    )


def norm_name(s: str) -> str:
    s = _strip_accents(s or "")
    s = s.lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def load_names_index() -> Optional[Dict]:
    try:
        with open(NAMES_INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Names index file not found: {NAMES_INDEX_FILE}")
        return None
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in names index file: {e}")
        return None
    except Exception as e:
        print(f"Error loading names index from {NAMES_INDEX_FILE}: {e}")
        return None


def save_names_index(index: Dict) -> None:
    ensure_dir(INDEX_DIR)
    with open(NAMES_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def build_names_index(users: List[Dict[str, str]]) -> Dict:
    """
    Minimal index: num2id = { normalized_full_name: user_id }
    """
    num2id: Dict[str, str] = {}
    for u in users:
        uid = u.get("user_id", "")
        name = u.get("user_name", "")
        if not uid or not name:
            continue
        num2id[norm_name(name)] = uid
    return {"num2id": num2id}


def resolve_with_index(name_or_id: str, index: Dict) -> Optional[Tuple[str, str]]:
    # UUID passthrough
    
    q = norm_name(name_or_id)
    if not q:
        return None
    num2id: Dict[str, str] = index.get("num2id", {})
    
    if q in num2id:
        return num2id[q]
    # substring fallback
    for k, v in num2id.items():
        if q in k:
            return v
    return None

