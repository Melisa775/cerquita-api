from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_and_join_room_over_websocket():
    code = client.post("/api/rooms").json()["code"]
    assert client.get(f"/api/rooms/{code}").status_code == 200

    with client.websocket_connect(f"/ws/{code}?name=Ana") as ana:
        state = ana.receive_json()
        assert state["type"] == "room_state"
        assert state["host"] == "Ana"

        with client.websocket_connect(f"/ws/{code}?name=Leo") as leo:
            assert [p["name"] for p in leo.receive_json()["players"]] == ["Ana", "Leo"]
            assert len(ana.receive_json()["players"]) == 2

            ana.send_json({"type": "start_game", "game": "color", "rounds": 1})
            assert ana.receive_json()["game"]["phase"] == "memorize"

            leo.receive_json()
            leo.send_json({"type": "baile"})
            assert leo.receive_json() == {"type": "error", "message": "Acción desconocida"}


def test_unknown_room():
    assert client.get("/api/rooms/ZZZZZ").status_code == 404
    with client.websocket_connect("/ws/ZZZZZ?name=Ana") as ws:
        assert ws.receive_json()["fatal"] is True
