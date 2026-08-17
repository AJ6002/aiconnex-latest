"""
plugins/registry.py - Deterministic Central Plugin Registry
============================================================
Provides auto-discovery, registration, and deterministic plugin selection:
  1. Explicit Policy Override (from dataset manifest or user config)
  2. Plugin Priority (declared in plugin metadata)
  3. Specificity / Confidence Score from probe() (minimum threshold 0.70)
  4. Fail closed on ambiguity (raises AmbiguousPluginMatchError)
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type

from .base import BasePlugin, MatchResult
from .context import PipelineContext, PluginSnapshot, ResolvedPlugin

logger = logging.getLogger(__name__)


class AmbiguousPluginMatchError(Exception):
    """Raised when two or more plugins score equally above threshold without explicit override."""
    pass


class UnsupportedLayoutError(Exception):
    """Raised when no plugin passes the minimum confidence threshold (0.70)."""
    pass


class UnsupportedFormatError(Exception):
    """Raised when an uploaded file format is outside the scope of registered plugins."""
    SUPPORTED_FORMATS = [
        "csv", "tsv", "txt", "xlsx", "xls", "parquet", "json", "jsonl",
        "mat", "hdf5", "h5", "tdms", "sqlite", "db", "xml", "scada_excel"
    ]

    def __init__(self, ext: str):
        self.ext = ext
        msg = (
            f"Format '{ext}' is not supported by the AIConnex compiler.\n"
            f"Supported formats: {', '.join(self.SUPPORTED_FORMATS)}\n"
            f"If your format is different, please convert it manually to a supported format first."
        )
        super().__init__(msg)



class PluginRegistry:
    """
    Central Singleton Registry for compiler plugins across all 5 stages.
    Enforces startup-only discovery, deterministic resolution, and lockfile snapshotting.
    """

    MIN_CONFIDENCE_THRESHOLD = 0.70
    _instance: Optional[PluginRegistry] = None

    # Supported contract versions for this registry
    SUPPORTED_CONTRACT_VERSIONS = {1}

    def __init__(self) -> None:
        # stage -> list of registered BasePlugin instances
        self._registered: Dict[str, List[BasePlugin]] = {
            "discovery": [],
            "parser": [],
            "assembler": [],
            "harvester": [],
            "normalizer": [],
        }
        self._is_frozen = False

    @classmethod
    def get_instance(cls) -> PluginRegistry:
        if cls._instance is None:
            cls._instance = PluginRegistry()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset instance for clean unit testing."""
        cls._instance = None

    def register(self, plugin: BasePlugin) -> None:
        """Register a plugin instance into its corresponding stage."""
        if self._is_frozen:
            raise RuntimeError("PluginRegistry is frozen for execution. Cannot register new plugins mid-run.")
        
        stage = plugin.stage.lower()
        if stage not in self._registered:
            raise ValueError(f"Unknown plugin stage '{stage}'. Supported: {list(self._registered.keys())}")

        # Validate contract_version compatibility
        contract_ver = getattr(plugin, "contract_version", 1)
        if contract_ver not in self.SUPPORTED_CONTRACT_VERSIONS:
            logger.warning(
                f"[PluginRegistry] Rejecting plugin '{plugin.plugin_id}' v{plugin.version}: "
                f"contract_version={contract_ver} not in supported set {self.SUPPORTED_CONTRACT_VERSIONS}"
            )
            return

        # Enforce single active version per plugin_id per stage
        existing = [p for p in self._registered[stage] if p.plugin_id == plugin.plugin_id]
        if existing:
            logger.warning(f"[PluginRegistry] Replacing plugin_id '{plugin.plugin_id}' v{existing[0].version} with v{plugin.version}")
            self._registered[stage].remove(existing[0])

        self._registered[stage].append(plugin)
        logger.debug(f"[PluginRegistry] Registered '{plugin.plugin_id}' v{plugin.version} in stage '{stage}'")

    def get_plugins(self, stage: str) -> List[BasePlugin]:
        """Return all registered plugins for a given stage."""
        return self._registered.get(stage.lower(), [])

    def auto_discover(self, plugins_dir: Optional[Path] = None) -> None:
        """Startup-only discovery: imports all sub-packages in plugins/ to trigger registration."""
        if self._is_frozen:
            return

        base_path = plugins_dir or Path(__file__).parent
        stage_dirs = ["discovery", "parsers", "assemblers", "harvesters", "normalizers"]

        for s_dir in stage_dirs:
            stage_path = base_path / s_dir
            if stage_path.exists() and stage_path.is_dir():
                for file_p in stage_path.glob("*.py"):
                    if file_p.name.startswith("__"):
                        continue
                    mod_name = file_p.stem
                    pkg = __package__ or "services.aiconnex_zip_compiler.plugins"
                    full_module_name = f"{pkg}.{s_dir}.{mod_name}"
                    try:
                        if full_module_name in sys.modules:
                            importlib.reload(sys.modules[full_module_name])
                        else:
                            importlib.import_module(full_module_name)
                    except Exception as e:
                        try:
                            fallback_name = f"aiconnex_zip_compiler.plugins.{s_dir}.{mod_name}"
                            importlib.import_module(fallback_name)
                        except Exception as e2:
                            logger.warning(f"[PluginRegistry] Auto-discovery failed for '{full_module_name}': {e} / {e2}")

    def resolve(self, stage: str, context: PipelineContext) -> BasePlugin:
        """
        Deterministic plugin selection algorithm:
          Winner = argmax(policy_override, priority, confidence)
          Condition: supported=True and confidence >= 0.70.
          Fail-closed if top two plugins tie.
        """
        stage = stage.lower()
        candidates = self._registered.get(stage, [])
        if not candidates:
            raise UnsupportedLayoutError(f"No plugins registered for stage '{stage}'")

        # 1. Policy Override check
        override_id = context.policy_overrides.get(stage)
        if override_id:
            for plugin in candidates:
                if plugin.plugin_id == override_id:
                    logger.info(f"[PluginRegistry] Policy override selected '{plugin.plugin_id}' for stage '{stage}'")
                    return plugin
            raise UnsupportedLayoutError(f"Policy override plugin_id '{override_id}' not found in stage '{stage}'")

        # 2. Probe candidates and collect scores
        probed_results: List[Tuple[BasePlugin, MatchResult]] = []
        for plugin in candidates:
            try:
                res = plugin.probe(context)
                if res.supported and res.confidence >= self.MIN_CONFIDENCE_THRESHOLD:
                    probed_results.append((plugin, res))
            except Exception as e:
                logger.warning(f"[PluginRegistry] Plugin '{plugin.plugin_id}' probe error: {e}")

        if not probed_results:
            raise UnsupportedLayoutError(f"No plugin passed minimum confidence threshold ({self.MIN_CONFIDENCE_THRESHOLD}) for stage '{stage}'")

        # 3. Sort by priority desc, then confidence desc
        probed_results.sort(key=lambda item: (item[0].priority, item[1].confidence), reverse=True)

        top_plugin, top_res = probed_results[0]

        # 4. Check for tie (fail closed if top two have identical priority and confidence)
        if len(probed_results) > 1:
            second_plugin, second_res = probed_results[1]
            if (second_plugin.priority == top_plugin.priority and 
                abs(second_res.confidence - top_res.confidence) < 1e-4):
                raise AmbiguousPluginMatchError(
                    f"Ambiguous match in stage '{stage}': Both '{top_plugin.plugin_id}' and '{second_plugin.plugin_id}' "
                    f"scored priority={top_plugin.priority}, confidence={top_res.confidence:.2f}. "
                    "Fail-closed: explicit policy override required."
                )

        logger.info(
            f"[PluginRegistry] Resolved '{top_plugin.plugin_id}' v{top_plugin.version} for stage '{stage}' "
            f"(priority={top_plugin.priority}, confidence={top_res.confidence:.2f})"
        )
        return top_plugin

    def freeze(self) -> PluginSnapshot:
        """Freeze registry and return immutable PluginSnapshot for the run."""
        self._is_frozen = True
        resolved = {}
        for stage, plugins in self._registered.items():
            for p in plugins:
                # Key by plugin_id so ALL active plugins are recorded, not just one per stage
                resolved[p.plugin_id] = ResolvedPlugin(
                    plugin_id=p.plugin_id,
                    version=p.version,
                    contract_version=p.contract_version,
                    stage=p.stage,
                    priority=p.priority,
                )
        return PluginSnapshot(
            compiler_version="0.9.0-plugin",
            run_timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            resolved_plugins=resolved,
        )


def register_plugin(plugin_cls: Type[BasePlugin]) -> Type[BasePlugin]:
    """Decorator to register a plugin class into the global PluginRegistry."""
    registry = PluginRegistry.get_instance()
    instance = plugin_cls()
    registry.register(instance)
    return plugin_cls
