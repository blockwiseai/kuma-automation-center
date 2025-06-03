from fastapi.testclient import TestClient
from app.main import app
import json
from datetime import datetime

client = TestClient(app)

def test_monitor_notification():
    test_notification = {
        "monitorID": 1,
        "monitor": "Test Server",
        "status": 0,
        "msg": "Server is down",
        "time": datetime.now().isoformat(),
        "important": True,
        "ping": 1500,
        "duration": 2000,
        "extra": {
            "error": "Connection timeout"
        }
    }

    response = client.post("/webhook", json=test_notification)
    assert response.status_code == 200
    assert response.json()["status"] == "received"
    assert response.json()["notification"]["monitor"] == "Test Server"