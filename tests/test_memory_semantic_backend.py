# tests/test_memory_semantic_backend.py
import os
import pytest

from agentic.memory.backends.local_fake import LocalFakeBackend
from agentic.memory.backends.factory import get_semantic_backend, reset_semantic_backend


@pytest.fixture(autouse=True)
def _clean_backend():
    reset_semantic_backend()
    os.environ.pop("AICONNEX_MEMORY_BACKEND", None)
    yield
    reset_semantic_backend()
    os.environ.pop("AICONNEX_MEMORY_BACKEND", None)


def test_local_fake_backend_ranks_matching_text_first():
    backend = LocalFakeBackend()
    backend.add("NASA FD001 turbofan engine dataset, 26898 rows", {"subject_id": "ds_nasa_fd001"})
    backend.add("Bearing vibration dataset from IMS testbed", {"subject_id": "ds_ims_bearing"})
    backend.add("SCADA compressor telemetry dataset", {"subject_id": "ds_scada"})

    results = backend.search("turbofan engine rows", limit=3)

    assert len(results) > 0
    assert results[0]["metadata"]["subject_id"] == "ds_nasa_fd001"
    assert results[0]["score"] > 0


def test_local_fake_backend_no_match_returns_empty_or_zero_scores():
    backend = LocalFakeBackend()
    backend.add("NASA FD001 turbofan engine dataset", {"subject_id": "ds_nasa_fd001"})

    results = backend.search("completely unrelated query about weather", limit=3)
    assert all(r["score"] == 0 for r in results) or results == []


def test_get_semantic_backend_defaults_to_local_fake():
    backend = get_semantic_backend()
    assert isinstance(backend, LocalFakeBackend)


def test_get_semantic_backend_is_a_singleton():
    b1 = get_semantic_backend()
    b2 = get_semantic_backend()
    assert b1 is b2


def test_reset_semantic_backend_yields_fresh_empty_instance():
    backend1 = get_semantic_backend()
    backend1.add("some memory", {"subject_id": "ds_1"})
    reset_semantic_backend()
    backend2 = get_semantic_backend()
    assert backend2 is not backend1
    assert backend2.search("some memory") == []


def test_mem0_backend_selection_without_install_raises_clear_error():
    os.environ["AICONNEX_MEMORY_BACKEND"] = "mem0"
    reset_semantic_backend()
    try:
        get_semantic_backend()
        # If mem0ai happens to be installed in this environment, no error is raised -
        # that's fine, just skip the assertion in that case.
    except RuntimeError as e:
        assert "mem0ai" in str(e).lower()
    except ConnectionError:
        # mem0ai is installed but Ollama is not running — this is an infrastructure
        # issue, not a code bug. Skip instead of fail.
        pytest.skip("Ollama service not running; skipping mem0 backend selection test")
