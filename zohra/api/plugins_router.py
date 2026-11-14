# ZOHRA OS — Plugin API Router & Management Gateway
import logging
from typing import Dict, Any
from pydantic import BaseModel

try:
    from fastapi import APIRouter, HTTPException
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

if FASTAPI_AVAILABLE:
    from zohra.services.plugins.plugin_manager import PluginManager

    logger = logging.getLogger("zohra.api.plugins")
    router = APIRouter(prefix="/api/v1/plugins", tags=["Plugin Ecosystem Services"])
    
    manager = PluginManager()

    class PluginActionPayload(BaseModel):
        plugin_id: str

    @router.get("")
    async def list_plugins():
        """Lists all installed plugins, manifests, and active statuses."""
        try:
            results = []
            for pid, manifest in manager.manifests.items():
                results.append({
                    "id": pid,
                    "name": manifest.get("name"),
                    "version": manifest.get("version"),
                    "description": manifest.get("description"),
                    "author": manifest.get("author"),
                    "status": manager.statuses.get(pid, "DISABLED")
                })
            return {"status": "success", "plugins": results}
        except Exception as e:
            logger.error(f"Failed to list plugins: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/enable")
    async def enable_plugin(payload: PluginActionPayload):
        """Enables a plugin by ID."""
        try:
            from zohra.event_bus import event_bus
            success = await manager.enable_plugin(payload.plugin_id, {"event_bus": event_bus, "logger": logger})
            if success:
                return {"status": "success", "message": f"Plugin '{payload.plugin_id}' enabled."}
            else:
                raise HTTPException(status_code=400, detail="Failed to enable plugin. Check logs.")
        except Exception as e:
            logger.error(f"Failed to enable plugin: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/disable")
    async def disable_plugin(payload: PluginActionPayload):
        """Disables a plugin by ID."""
        try:
            success = await manager.disable_plugin(payload.plugin_id)
            if success:
                return {"status": "success", "message": f"Plugin '{payload.plugin_id}' disabled."}
            else:
                raise HTTPException(status_code=400, detail="Failed to disable plugin.")
        except Exception as e:
            logger.error(f"Failed to disable plugin: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/marketplace")
    async def list_marketplace_plugins():
        """Report marketplace availability without presenting an unconfigured catalog as live."""
        return {
            "status": "unavailable",
            "plugins": [],
            "message": "No marketplace provider is configured.",
        }
else:
    router = None
