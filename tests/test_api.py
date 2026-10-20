import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient
from conductor.api import create_app


def test_api_controls():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "t.db")
    app = create_app(db_path=db)
    client = TestClient(app)
    # create run
    r = client.post("/api/runs", json={"objective": "hello", "concurrency": 1, "use_opencode": False})
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    # pause/resume/cancel
    assert client.post(f"/api/runs/{run_id}/pause").status_code == 200
    assert client.post(f"/api/runs/{run_id}/resume").status_code == 200
    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 200
    # status endpoints
    assert client.get(f"/api/runs/{run_id}/tasks").status_code == 200