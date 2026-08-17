"""
tests/test_source_register.py

Unit test suite for Platform KB SourceRegisterManager.
"""

import os
import pytest
from agentic.platform_kb.source_register import SourceRegisterManager, DEFAULT_REGISTER_CSV


def test_source_register_manager_loads_approved_sources():
    manager = SourceRegisterManager()
    all_approved = manager.get_approved_sources(domain="all")
    platform_approved = manager.get_approved_sources(domain="platform")
    dataset_approved = manager.get_approved_sources(domain="dataset")
    
    assert len(all_approved) >= 8
    assert len(platform_approved) >= 6
    assert len(dataset_approved) == 2
    for src in all_approved:
        assert src.status == "Approved"
        assert src.authority_level in ("A", "B", "C")


def test_source_register_load_all_sources_unfiltered():
    manager = SourceRegisterManager()
    all_sources = manager.load_all_sources()
    assert len(all_sources) >= 8
    for src in all_sources:
        assert src.source_id.startswith(("PLAT-", "DATA-", "IND-", "SRC-IND-", "TERM-", "ML-"))


def test_source_register_get_by_id():
    manager = SourceRegisterManager()
    doc1 = manager.get_source_by_id("PLAT-DOC-001")
    
    assert doc1 is not None
    assert doc1.title == "AIConnex Master Final Architecture"
    assert os.path.exists(doc1.source_location)


def test_source_register_get_by_nonexistent_id_returns_none():
    manager = SourceRegisterManager()
    nonexistent = manager.get_source_by_id("NONEXISTENT-ID-999")
    assert nonexistent is None


def test_source_register_caching_and_clear_cache():
    manager = SourceRegisterManager()
    records_1 = manager.load_all_sources()
    records_2 = manager.load_all_sources()
    
    # Assert identical cached object reference
    assert records_1 is records_2
    
    # Clear cache and reload
    manager.clear_cache()
    records_3 = manager.load_all_sources(force_reload=True)
    assert records_1 is not records_3
    assert len(records_1) == len(records_3)


def test_source_register_missing_file_raises_error():
    manager = SourceRegisterManager(register_path="nonexistent/path/to/register.csv")
    with pytest.raises(FileNotFoundError, match="Source register CSV not found"):
        manager.load_all_sources()

