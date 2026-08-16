from fastapi.responses import JSONResponse


async def health_check():
    return JSONResponse({"status": "ok"})
