"""
Helios Trading System V3.0 - Module Loader
Dynamic module loading with hot-reload capability
Following MODULAR_ARCHITECTURE_GUIDE.md specification
"""

import importlib
import sys
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio

from src.utils.logger import get_logger

logger = get_logger(__name__, component="modular_architecture")


class ModuleState(str, Enum):
    """Module lifecycle states"""
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ACTIVE = "active"
    FAILED = "failed"
    RELOADING = "reloading"


@dataclass
class ModuleMetadata:
    """Module configuration and state tracking"""
    name: str
    module_path: str
    version: str
    dependencies: List[str] = field(default_factory=list)
    hot_reloadable: bool = True
    state: ModuleState = ModuleState.UNLOADED
    instance: Optional[Any] = None
    load_time: Optional[datetime] = None
    error: Optional[str] = None
    reload_count: int = 0


class ModuleLoader:
    """
    Dynamic module loader with hot-reload capability.

    Features:
    - Load/unload modules at runtime
    - Dependency management
    - Hot-swap with rollback on failure
    - Module state tracking
    - Reload hooks for post-reload initialization
    """

    def __init__(self):
        self._modules: Dict[str, ModuleMetadata] = {}
        self._reload_hooks: Dict[str, List[Callable]] = {}
        self._lock = asyncio.Lock()

    async def register_module(
        self,
        name: str,
        module_path: str,
        version: str,
        dependencies: Optional[List[str]] = None,
        hot_reloadable: bool = True
    ) -> None:
        """
        Register a module for loading.

        Args:
            name: Module identifier (e.g., "neural_predictor_v2")
            module_path: Python import path (e.g., "src.ml.inference.neural_predictor_v2")
            version: Version string (e.g., "2.0.0")
            dependencies: List of module names this module depends on
            hot_reloadable: Whether module can be hot-reloaded
        """
        async with self._lock:
            if name in self._modules:
                logger.warning(f"Module {name} already registered, updating metadata")

            metadata = ModuleMetadata(
                name=name,
                module_path=module_path,
                version=version,
                dependencies=dependencies or [],
                hot_reloadable=hot_reloadable
            )

            self._modules[name] = metadata
            logger.info(f"Module registered: {name} (v{version})")

    async def load_module(self, name: str, force_reload: bool = False) -> Any:
        """
        Load a module and return its instance.

        Args:
            name: Module name
            force_reload: Force reload even if already loaded

        Returns:
            Module instance

        Raises:
            ValueError: If module not registered or dependencies not met
            ImportError: If module cannot be imported
        """
        async with self._lock:
            if name not in self._modules:
                raise ValueError(f"Module {name} not registered")

            metadata = self._modules[name]

            # Check if already loaded
            if metadata.state == ModuleState.LOADED and not force_reload:
                logger.info(f"Module {name} already loaded, returning cached instance")
                return metadata.instance

            # Check dependencies
            await self._check_dependencies(metadata)

            # Update state
            metadata.state = ModuleState.LOADING if not force_reload else ModuleState.RELOADING
            logger.info(f"Loading module: {name} from {metadata.module_path}")

            try:
                # Import module
                module = importlib.import_module(metadata.module_path)

                # Reload if forcing
                if force_reload:
                    module = importlib.reload(module)
                    metadata.reload_count += 1

                # Get module instance (assume module has default export or class)
                # For now, return the module itself
                instance = module

                # Update metadata
                metadata.instance = instance
                metadata.state = ModuleState.LOADED
                metadata.load_time = datetime.utcnow()
                metadata.error = None

                logger.info(f"Module {name} loaded successfully (reload count: {metadata.reload_count})")

                # Execute reload hooks
                if force_reload and name in self._reload_hooks:
                    await self._execute_reload_hooks(name, instance)

                return instance

            except Exception as e:
                metadata.state = ModuleState.FAILED
                metadata.error = str(e)
                logger.error(f"Failed to load module {name}: {e}", exc_info=True)
                raise

    async def unload_module(self, name: str) -> bool:
        """
        Unload a module.

        Args:
            name: Module name

        Returns:
            True if successfully unloaded
        """
        async with self._lock:
            if name not in self._modules:
                logger.warning(f"Module {name} not registered")
                return False

            metadata = self._modules[name]

            if metadata.state == ModuleState.UNLOADED:
                logger.info(f"Module {name} already unloaded")
                return True

            logger.info(f"Unloading module: {name}")

            try:
                # Remove from sys.modules to allow reimport
                if metadata.module_path in sys.modules:
                    del sys.modules[metadata.module_path]

                # Clear instance
                metadata.instance = None
                metadata.state = ModuleState.UNLOADED

                logger.info(f"Module {name} unloaded successfully")
                return True

            except Exception as e:
                logger.error(f"Failed to unload module {name}: {e}", exc_info=True)
                return False

    async def swap_module(
        self,
        name: str,
        new_version_path: str,
        rollback_on_failure: bool = True
    ) -> bool:
        """
        Hot-swap a module with a new version.

        Args:
            name: Module name
            new_version_path: New module path
            rollback_on_failure: Rollback to old version if swap fails

        Returns:
            True if swap successful
        """
        async with self._lock:
            if name not in self._modules:
                raise ValueError(f"Module {name} not registered")

            metadata = self._modules[name]

            if not metadata.hot_reloadable:
                raise ValueError(f"Module {name} is not hot-reloadable")

            # Save old state for rollback
            old_path = metadata.module_path
            old_instance = metadata.instance
            old_state = metadata.state

            logger.info(f"Hot-swapping module {name}: {old_path} → {new_version_path}")

            try:
                # Update path
                metadata.module_path = new_version_path

                # Unload old
                await self.unload_module(name)

                # Load new
                new_instance = await self.load_module(name, force_reload=True)

                logger.info(f"Module {name} swapped successfully")
                return True

            except Exception as e:
                logger.error(f"Failed to swap module {name}: {e}", exc_info=True)

                if rollback_on_failure:
                    logger.warning(f"Rolling back module {name} to previous version")
                    try:
                        # Restore old state
                        metadata.module_path = old_path
                        metadata.instance = old_instance
                        metadata.state = old_state

                        logger.info(f"Module {name} rolled back successfully")
                    except Exception as rollback_error:
                        logger.error(f"Rollback failed for {name}: {rollback_error}", exc_info=True)
                        metadata.state = ModuleState.FAILED

                return False

    def add_reload_hook(self, name: str, hook: Callable) -> None:
        """
        Add a hook to execute after module reload.

        Args:
            name: Module name
            hook: Async callable to execute after reload
        """
        if name not in self._reload_hooks:
            self._reload_hooks[name] = []

        self._reload_hooks[name].append(hook)
        logger.info(f"Reload hook added for module {name}")

    async def _execute_reload_hooks(self, name: str, instance: Any) -> None:
        """Execute all reload hooks for a module"""
        if name not in self._reload_hooks:
            return

        logger.info(f"Executing {len(self._reload_hooks[name])} reload hooks for {name}")

        for hook in self._reload_hooks[name]:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(instance)
                else:
                    hook(instance)
            except Exception as e:
                logger.error(f"Reload hook failed for {name}: {e}", exc_info=True)

    async def _check_dependencies(self, metadata: ModuleMetadata) -> None:
        """
        Check if all dependencies are loaded.

        Raises:
            ValueError: If dependencies not met
        """
        for dep_name in metadata.dependencies:
            if dep_name not in self._modules:
                raise ValueError(f"Dependency {dep_name} not registered for module {metadata.name}")

            dep_metadata = self._modules[dep_name]
            if dep_metadata.state != ModuleState.LOADED:
                # Try to load dependency
                logger.info(f"Loading dependency {dep_name} for {metadata.name}")
                await self.load_module(dep_name)

    def get_module_status(self, name: str) -> Dict[str, Any]:
        """
        Get module status information.

        Args:
            name: Module name

        Returns:
            Status dictionary
        """
        if name not in self._modules:
            return {"error": f"Module {name} not registered"}

        metadata = self._modules[name]

        return {
            "name": metadata.name,
            "version": metadata.version,
            "state": metadata.state.value,
            "hot_reloadable": metadata.hot_reloadable,
            "dependencies": metadata.dependencies,
            "load_time": metadata.load_time.isoformat() if metadata.load_time else None,
            "reload_count": metadata.reload_count,
            "error": metadata.error
        }

    def get_all_modules_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status for all registered modules"""
        return {
            name: self.get_module_status(name)
            for name in self._modules.keys()
        }


# Global module loader instance
module_loader = ModuleLoader()
