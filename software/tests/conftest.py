import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


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
