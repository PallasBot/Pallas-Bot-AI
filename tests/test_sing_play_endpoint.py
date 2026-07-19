from fastapi.testclient import TestClient

from app.main import create_app


def test_post_play_endpoint_accepts_request_body(monkeypatch) -> None:
    async def fake_play(request_id: str, speaker: str = "") -> str:
        assert request_id == "req-123"
        assert speaker == "pallas"
        return "task-123"

    monkeypatch.setattr("app.api.endpoints.sing.play", fake_play)
    client = TestClient(create_app(enabled_endpoints={"sing"}))

    response = client.post("/api/play/req-123", json={"speaker": "pallas"})

    assert response.status_code == 200
    assert response.json() == {"task_id": "task-123", "status": "processing"}


def test_legacy_get_play_endpoint_is_disabled() -> None:
    client = TestClient(create_app(enabled_endpoints={"sing"}))

    response = client.get("/api/play/amiya")

    assert response.status_code == 410
    assert response.json()["detail"] == "legacy play disabled; use POST /api/play/{request_id}"
