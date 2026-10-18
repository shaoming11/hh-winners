"""Read-only public face of the bench backend, for the hosted dashboard (autochem on Vercel) through a tunnel.

    python tools/public_proxy.py                 # :8001 -> the backend on :8000
    cloudflared tunnel --url http://127.0.0.1:8001

Only what the dashboard needs to WATCH is passed: the live feed (/events), the camera (/stream.mjpg, snapshots),
the state, and the harmless view verbs (camera choice, mouse orbit). Everything that could move hardware or change a
run - /api/command (hw_replay, arm goals), start / stop / reset / mode, approvals, messages, /mcp - is refused,
because the tunnel URL is public and the backend's operator commands need no approval.
"""
import os
import re

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

BACKEND = os.environ.get("AUTOCHEM_BACKEND", "http://127.0.0.1:8000")
GET_OK = re.compile(r"^/(events|stream\.mjpg|api/stream\.mjpg|api/state|api/snapshot/[\w-]+\.jpg|api/describe|replay/tape\.json)$")
POST_OK = re.compile(r"^/api/(view|camera/[\w-]+)$")
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "content-type"}
client = httpx.AsyncClient(base_url=BACKEND, timeout=httpx.Timeout(10.0, read=None))


async def proxy(request: Request):
    path = request.url.path
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=CORS)
    allowed = (request.method in ("GET", "HEAD") and GET_OK.match(path)) or (request.method == "POST" and POST_OK.match(path))
    if not allowed:
        return JSONResponse({"ok": False, "message": "read-only public view: control the bench from the lab"},
                            status_code=403, headers=CORS)
    body = await request.body()
    req = client.build_request(request.method, path, params=request.query_params, content=body or None,
                               headers={k: v for k, v in request.headers.items() if k.lower() in ("content-type", "accept")})
    r = await client.send(req, stream=True)
    hdr = {k: v for k, v in r.headers.items() if k.lower() in ("content-type", "cache-control")}
    hdr.update(CORS); hdr["X-Accel-Buffering"] = "no"

    async def body_iter():
        try:
            async for chunk in r.aiter_raw():
                yield chunk
        finally:
            await r.aclose()
    return StreamingResponse(body_iter(), status_code=r.status_code, headers=hdr)


app = Starlette(routes=[Route("/{path:path}", proxy, methods=["GET", "HEAD", "POST", "OPTIONS", "PUT", "DELETE", "PATCH"])])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("AUTOCHEM_PROXY_PORT", "8001")))
