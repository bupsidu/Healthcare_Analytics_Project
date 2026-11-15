import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import docs_urls


class DocsVisibilityTests(unittest.TestCase):
    def test_docs_are_on_by_default(self):
        self.assertTrue(Settings(SECRET_KEY="x", _env_file=None).ENABLE_DOCS)

    def test_disabled_docs_return_404(self):
        client = TestClient(FastAPI(**docs_urls(False)))
        for path in ("/docs", "/redoc", "/api/openapi.json"):
            self.assertEqual(client.get(path).status_code, 404, path)

    def test_enabled_docs_are_served(self):
        client = TestClient(FastAPI(**docs_urls(True)))
        for path in ("/docs", "/redoc", "/api/openapi.json"):
            self.assertEqual(client.get(path).status_code, 200, path)


if __name__ == "__main__":
    unittest.main()
