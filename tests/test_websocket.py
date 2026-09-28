import unittest
from fastapi.testclient import TestClient
from app.server import app

class TestWebSocketEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_websocket_empty_prompt_validation(self):
        with self.client.websocket_connect("/ws/query") as ws:
            ws.send_json({"prompt": "", "models": ["Gemini"]})
            data = ws.receive_json()
            self.assertEqual(data["type"], "error")
            self.assertIn("empty", data["message"].lower())

if __name__ == "__main__":
    unittest.main()
