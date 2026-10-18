import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "benchsim"))   # benchsim is a sibling package

# Set BEFORE any test module imports backend.app, which builds its Store at import time.  Without
# this the suite's chat/people/run records land in the demo's shared out/backend - test handles
# like "+1999" used to pile up in out/backend/people.json and run folders in out/backend/runs.
os.environ.setdefault("WLB_BACKEND_DIR", tempfile.mkdtemp(prefix="wlb-test-store-"))
os.environ.setdefault("WLB_PLAN_MODE", "full")      # the tests were written against the full process


@pytest.fixture(scope="session")
def app_client():
    """ONE FastAPI TestClient for the whole session.  Entering the app lifespan starts the MCP
    StreamableHTTPSessionManager, whose run() may only be called once per process, so every test
    module shares this instead of opening its own client.  Yields (client, backend.app module)."""
    os.environ["WLB_RENDER"] = "0"
    os.environ["WLB_AUTOCONNECT"] = "0"
    from fastapi.testclient import TestClient
    import backend.app as appmod
    if appmod.runner.b is None:
        appmod.runner.connect()
    with TestClient(appmod.app) as c:
        yield c, appmod
