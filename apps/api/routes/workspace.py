import shutil

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["workspace"])


def _get_ctx(workspace_id: str, session_id: str = "default"):
    from apps.api.main import get_or_create_session
    return get_or_create_session(session_id, workspace_id)


@router.post("/reset")
async def reset_workspace(workspace_id: str = "default", session_id: str = "default"):
    ctx = _get_ctx(workspace_id, session_id)
    try:
        for item in ctx.workspace_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)
        from apps.api.realtime.socket_server import sio
        await sio.emit("files.changed")
        return JSONResponse({"success": True, "message": "Workspace reset successfully"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
