import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from services.agent.gateway.policy import PolicyEngine

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["files"])


def _get_ctx(workspace_id: str, session_id: str = "default"):
    """Resolve session context — imported lazily to avoid circular imports."""
    from apps.api.main import get_or_create_session
    return get_or_create_session(session_id, workspace_id)


@router.get("/files")
async def list_files(workspace_id: str = "default", session_id: str = "default"):
    ctx = _get_ctx(workspace_id, session_id)
    res = await ctx.sandbox.list_dir("", recursive=True)
    if not res.success:
        raise HTTPException(status_code=400, detail=res.error)

    def format_tree(items):
        tree = []
        for it in items:
            node = {"name": it.name, "type": it.type, "path": it.path}
            if it.children is not None:
                node["children"] = format_tree(it.children)
            tree.append(node)
        return tree

    return JSONResponse(content=format_tree(res.items))


@router.get("/files/content")
async def get_file_content(path: str = Query(...), workspace_id: str = "default", session_id: str = "default"):
    ctx = _get_ctx(workspace_id, session_id)
    res = await ctx.sandbox.read_file(path)
    if not res.success:
        raise HTTPException(status_code=404 if "not found" in (res.error or "").lower() else 400, detail=res.error)
    return PlainTextResponse(res.content or "")


@router.put("/files/content")
async def save_file(request: Request, workspace_id: str = "default", session_id: str = "default"):
    data = await request.json()
    path = data.get("path")
    content = data.get("content")
    if not path or content is None:
        raise HTTPException(status_code=400, detail="Missing path or content")

    ctx = _get_ctx(workspace_id, session_id)
    res = await ctx.sandbox.write_file(path, content)
    if not res.success:
        raise HTTPException(status_code=400, detail=res.error)
    return JSONResponse({"success": True, "path": path, "diff": res.diff})


@router.post("/files")
async def create_file_or_folder(request: Request, workspace_id: str = "default", session_id: str = "default"):
    """Create a file or folder. Body: { path: str, type?: 'file'|'folder', content?: str }"""
    data = await request.json()
    path = data.get("path")
    item_type = data.get("type", "file")
    content = data.get("content", "")

    if not path:
        raise HTTPException(status_code=400, detail="Missing path")

    ctx = _get_ctx(workspace_id, session_id)
    full_path = (ctx.workspace_dir / path.lstrip("/")).resolve()

    # Security: ensure inside workspace
    if not str(full_path).startswith(str(ctx.workspace_dir)):
        raise HTTPException(status_code=403, detail="Path outside workspace")

    try:
        if item_type == "folder":
            full_path.mkdir(parents=True, exist_ok=True)
        else:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")

        from apps.api.realtime.socket_server import sio
        await sio.emit("files.changed")
        return JSONResponse({"success": True, "path": path, "type": item_type})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/files")
async def delete_file(
    request: Request,
    path: Optional[str] = Query(None),
    workspace_id: str = "default",
    session_id: str = "default",
):
    ctx = _get_ctx(workspace_id, session_id)
    target_path = path
    if not target_path:
        try:
            body = await request.json()
            target_path = body.get("path")
        except Exception:
            pass

    if not target_path:
        raise HTTPException(status_code=400, detail="Missing path parameter")

    clean_path = str(target_path).lstrip("/").strip()
    valid, full_path, err = PolicyEngine.resolve_and_validate_path(ctx.workspace_dir, clean_path)
    if not valid or not full_path or not full_path.exists():
        full_path = (ctx.workspace_dir / clean_path).resolve()
        if not full_path.exists():
            return JSONResponse({"success": True, "path": clean_path, "note": "Already removed"})

    try:
        if full_path.is_dir():
            shutil.rmtree(full_path, ignore_errors=True)
        else:
            full_path.unlink(missing_ok=True)
        from apps.api.realtime.socket_server import sio
        await sio.emit("files.changed")
        return JSONResponse({"success": True, "path": clean_path})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
