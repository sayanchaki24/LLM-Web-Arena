import unittest
from fastapi.testclient import TestClient
from app.server import app

class TestServerAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_get_index(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("BestResponse", response.text)

    def test_get_history(self):
        response = self.client.get("/api/history")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)

    def test_query_validation(self):
        response = self.client.post("/api/query", json={"prompt": ""})
        self.assertEqual(response.status_code, 400)

if __name__ == "__main__":
    unittest.main()
