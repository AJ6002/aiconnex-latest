"""
test_registry_lifecycle.py - Tests for PluginRegistry unfreeze & hot-reload lifecycle
===================================================================================
Verifies Gap 15 fix: dynamic unfreezing and reloading of the plugin registry.
"""

import pytest
from pathlib import Path
from services.aiconnex_zip_compiler.plugins.registry import PluginRegistry
from services.aiconnex_zip_compiler.plugins.base import BasePlugin, MatchResult
from services.aiconnex_zip_compiler.plugins.context import PipelineContext


class DummyPlugin(BasePlugin):
    plugin_id = "dummy_lifecycle_plugin"
    plugin_name = "Dummy Lifecycle Plugin"
    version = "1.0.0"
    stage = "discovery"
    priority = 10

    def probe(self, context: PipelineContext) -> MatchResult:
        return MatchResult(supported=True, confidence=0.80)

    def execute(self, context: PipelineContext) -> PipelineContext:
        return context


def test_registry_unfreeze_lifecycle():
    PluginRegistry.reset_instance()
    reg = PluginRegistry.get_instance()

    reg.freeze()
    assert reg._is_frozen is True

    # Registering while frozen should raise RuntimeError
    dummy = DummyPlugin()
    with pytest.raises(RuntimeError, match="PluginRegistry is frozen"):
        reg.register(dummy)

    # Test unfreeze
    reg.unfreeze()
    assert reg._is_frozen is False

    # Now registration should work
    reg.register(dummy)
    assert dummy in reg.get_plugins("discovery")


def test_registry_reload_and_unfreeze():
    PluginRegistry.reset_instance()
    reg = PluginRegistry.get_instance()

    reg.freeze()
    assert reg._is_frozen is True

    # Test reload_and_unfreeze
    reg.reload_and_unfreeze()
    assert reg._is_frozen is False
