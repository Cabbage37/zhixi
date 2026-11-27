"""Serve upstream API and production frontend on the same local origin."""
from pathlib import Path
import sys

source = Path(__file__).resolve().parent / "integrations/thinkflow"
sys.path.insert(0,str(source))
from fastapi_app.main import app
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse
import uvicorn

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

@app.middleware("http")
async def local_origin(request: Request, call_next):
    if request.headers.get("origin") not in (None, str(request.base_url).rstrip("/")):
        return JSONResponse({"detail":"Unsupported origin"},status_code=403)
    return await call_next(request)

@app.get("/zhixi-health")
def identity():
    return {"application":"zhixi-thinkflow"}

from marginalia_web import router as reader_router, SOURCE as reader_source
app.include_router(reader_router)
reader_web = reader_source / "zhixi/dist/web"
if reader_web.is_dir():
    app.mount("/marginalia", StaticFiles(directory=reader_web, html=True))
app.mount("/", StaticFiles(directory=source/"frontend/dist", html=True))
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=18766)
