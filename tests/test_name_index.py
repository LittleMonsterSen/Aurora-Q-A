import uuid
import app.name_index
from app.name_index import resolve_with_index, load_names_index



def test_resolve_with_full_index_exact_match():
    index = load_names_index()
    assert resolve_with_index("Sophia Al-Farsi", index) == "cd3a350e-dbd2-408f-afa0-16a072f56d23"


def test_resolve_with_full_index_substring():
    index = load_names_index()
    
    assert resolve_with_index("Sophia", index) == "cd3a350e-dbd2-408f-afa0-16a072f56d23"


def test_resolve_with_num2id_mapping_direct_is_not_supported():
    """
    Passing only the inner num2id mapping (dict[str,str]) is not supported by
    resolve_with_index, which expects the full index dict containing "num2id".
    Ensure it returns None so callers can correct usage to pass the full index.
    """
    num2id = load_names_index()
    assert resolve_with_index("Ethan", num2id) is None
