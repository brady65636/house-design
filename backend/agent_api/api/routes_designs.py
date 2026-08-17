"""Design Run metadata, immutable version history, activation, and restore APIs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field


router = APIRouter()


class RestoreVersionRequest(BaseModel):
    version_id: str = Field(min_length=1)


def _manager(request: Request):
    manager = getattr(request.app.state, "design_runs", None)
    if manager is None:
        raise HTTPException(status_code=503, detail="design_run_manager_unavailable")
    return manager


@router.get("/design-runs")
def list_design_runs(request: Request) -> dict:
    manager = _manager(request)
    return {
        "active_run_id": manager.active_run_id,
        "runs": [item.model_dump(mode="json") for item in manager.list_runs()],
    }


@router.get("/design-runs/{run_id}")
def get_design_run(run_id: str, request: Request) -> dict:
    try:
        return _manager(request).get_run(run_id).model_dump(mode="json")
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/design-runs/{run_id}/versions")
def list_versions(run_id: str, request: Request) -> dict:
    try:
        manager = _manager(request)
        return {
            "run_id": run_id,
            "current_version_id": manager.get_run(run_id).current_version_id,
            "versions": manager.list_versions(run_id),
        }
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/design-runs/{run_id}/activate")
def activate_design_run(run_id: str, request: Request) -> dict:
    try:
        return _manager(request).activate(run_id).model_dump(mode="json")
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/design-runs/{run_id}/restore")
def restore_version(run_id: str, body: RestoreVersionRequest, request: Request) -> dict:
    try:
        scheme = _manager(request).restore_version(run_id, body.version_id)
        return {"run_id": run_id, "scheme": scheme}
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
