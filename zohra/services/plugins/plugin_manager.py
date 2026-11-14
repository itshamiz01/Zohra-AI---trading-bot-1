# ZOHRA OS — Plugin Manager & SDK
import logging
import os
import json
import importlib.util
from typing import Dict, Any, List, Optional

logger = logging.getLogger("zohra.plugins.manager")

class BasePlugin:
    """Every Zohra OS Plugin must inherit from this class."""
    def __init__(self, context: Any):
        self.context = context
        self.enabled = False

    async def on_enable(self):
        """Triggered when the plugin is loaded and enabled."""
        pass

    async def on_disable(self):
        """Triggered when the plugin is disabled or uninstalled."""
        pass

    def get_tools(self) -> List[dict]:
        """Returns a list of tools/actions exposed by this plugin."""
        return []

class PluginManager:
    """Manages plugin discovery, manifests, loading, and lifecycle states."""
    def __init__(self, plugins_dir: str = "plugins"):
        self.plugins_dir = plugins_dir
        self.plugins: Dict[str, BasePlugin] = {}
        self.manifests: Dict[str, Dict[str, Any]] = {}
        self.statuses: Dict[str, str] = {} # "ENABLED", "DISABLED", "ERROR"
        
        # Ensure plugins directory exists and seed default plugin
        os.makedirs(self.plugins_dir, exist_ok=True)
        self.scan_plugins()

    def scan_plugins(self):
        """Scans the plugins directory and loads manifests."""
        logger.info(f"Scanning plugins in directory: {self.plugins_dir}")
        for folder in os.listdir(self.plugins_dir):
            folder_path = os.path.join(self.plugins_dir, folder)
            if os.path.isdir(folder_path):
                manifest_path = os.path.join(folder_path, "manifest.json")
                if os.path.exists(manifest_path):
                    try:
                        with open(manifest_path, "r") as f:
                            manifest = json.load(f)
                        plugin_id = manifest.get("id")
                        if plugin_id:
                            self.manifests[plugin_id] = manifest
                            self.statuses[plugin_id] = "DISABLED"
                            logger.info(f"Discovered plugin: '{manifest.get('name')}' ({plugin_id})")
                    except Exception as e:
                        logger.error(f"Failed to parse manifest in {folder}: {e}")

    async def enable_plugin(self, plugin_id: str, context: Any) -> bool:
        """Loads and activates a plugin by ID."""
        if plugin_id not in self.manifests:
            logger.error(f"Plugin {plugin_id} not found in manifests.")
            return False
            
        manifest = self.manifests[plugin_id]
        folder_name = [f for f in os.listdir(self.plugins_dir) if self._get_plugin_id(f) == plugin_id]
        if not folder_name:
            return False
            
        folder_path = os.path.join(self.plugins_dir, folder_name[0])
        entry_file = os.path.join(folder_path, manifest.get("entry_point", "plugin.py"))
        
        try:
            # Dynamically import the plugin module
            spec = importlib.util.spec_from_file_location(plugin_id, entry_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find the class inheriting from BasePlugin
            plugin_class = None
            for name, obj in module.__dict__.items():
                if isinstance(obj, type) and issubclass(obj, BasePlugin) and obj is not BasePlugin:
                    plugin_class = obj
                    break
                    
            if not plugin_class:
                raise AttributeError("No class inheriting from BasePlugin found in entry point.")
                
            # Instantiate and enable
            plugin_instance = plugin_class(context)
            await plugin_instance.on_enable()
            
            self.plugins[plugin_id] = plugin_instance
            self.statuses[plugin_id] = "ENABLED"
            logger.info(f"Successfully enabled plugin: {plugin_id}")
            return True
        except Exception as e:
            self.statuses[plugin_id] = "ERROR"
            logger.error(f"Failed to enable plugin {plugin_id}: {e}")
            return False

    async def disable_plugin(self, plugin_id: str) -> bool:
        """Deactivates a plugin by ID."""
        if plugin_id in self.plugins:
            try:
                await self.plugins[plugin_id].on_disable()
                self.plugins.pop(plugin_id)
                self.statuses[plugin_id] = "DISABLED"
                logger.info(f"Successfully disabled plugin: {plugin_id}")
                return True
            except Exception as e:
                logger.error(f"Error disabling plugin {plugin_id}: {e}")
        return False

    def _get_plugin_id(self, folder_name: str) -> Optional[str]:
        manifest_path = os.path.join(self.plugins_dir, folder_name, "manifest.json")
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r") as f:
                    return json.load(f).get("id")
            except Exception:
                pass
        return None
