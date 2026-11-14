"""Dashboard workspace read models. Reads never start engines or capture devices."""
from fastapi import APIRouter, Query
from zohra.analytics.workspace_data import research_snapshot, memory_snapshot, learning_snapshot, agent_snapshot

router = APIRouter(prefix="/api/v1", tags=["Workspaces"])


@router.get("/research")
def research():
    return research_snapshot()


@router.get("/memory")
def memory(q: str = Query("", max_length=300)):
    return memory_snapshot(q)


@router.get("/learning")
def learning():
    return learning_snapshot()


@router.get("/agents")
def agents():
    return agent_snapshot()
