# zohra/core/plugin_manager.py
import os
import sys
import importlib.util
import logging
from typing import Dict, Any, List

logger = logging.getLogger("zohra.core.plugin_manager")

class BasePlugin:
    """Base class for all ZOHRA OS Plugins."""
    def __init__(self, plugin_id: str, name: str, version: str):
        self.plugin_id = plugin_id
        self.name = name
        self.version = version
        self.enabled = True

    def initialize(self, core) -> bool:
        """Called when plugin is loaded into the core."""
        return True

    def shutdown(self) -> bool:
        """Called when plugin is disabled or core shuts down."""
        return True

class PluginManager:
    """Scans and dynamically loads plugins into ZOHRA OS Core."""
    def __init__(self, plugins_dir: str = None):
        if plugins_dir is None:
            self.plugins_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "plugins"
            )
        else:
            self.plugins_dir = plugins_dir
            
        os.makedirs(self.plugins_dir, exist_ok=True)
        self.plugins: Dict[str, BasePlugin] = {}

    def discover_and_load_plugins(self, core) -> List[str]:
        """Discovers and imports plugins from the plugins directory."""
        loaded = []
        if not os.path.exists(self.plugins_dir):
            return loaded

        # Ensure plugins dir is on path
        if self.plugins_dir not in sys.path:
            sys.path.insert(0, self.plugins_dir)

        for entry in os.scandir(self.plugins_dir):
            if entry.name.startswith("__") or entry.name == "base.py":
                continue
                
            plugin_name = None
            module = None
            
            try:
                if entry.is_file() and entry.name.endswith(".py"):
                    plugin_name = entry.name[:-3]
                    module = importlib.import_module(plugin_name)
                elif entry.is_dir() and os.path.exists(os.path.join(entry.path, "__init__.py")):
                    plugin_name = entry.name
                    module = importlib.import_module(plugin_name)
                    
                if module and hasattr(module, "register_plugin"):
                    plugin = module.register_plugin(core)
                    if isinstance(plugin, BasePlugin):
                        self.plugins[plugin.plugin_id] = plugin
                        loaded.append(plugin.name)
                        logger.info(f"Successfully loaded plugin: {plugin.name} v{plugin.version}")
            except Exception as e:
                logger.error(f"Failed to load plugin from {entry.name}: {e}", exc_info=True)
                
        return loaded

    def get_plugins_status(self) -> List[Dict[str, Any]]:
        """Returns details about all registered plugins."""
        status_list = []
        for pid, plugin in self.plugins.items():
            status_list.append({
                "plugin_id": plugin.plugin_id,
                "name": plugin.name,
                "version": plugin.version,
                "enabled": plugin.enabled
            })
        return status_list

# Central singleton instance
plugin_manager = PluginManager()
