import os
import json

# Use an in-memory SQLite DB for tests
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["UPLOAD_DIR"] = "./uploads_test"
os.environ["TESTING"] = "1"

from fastapi.testclient import TestClient
from app.main import app
from app.db.database import init_db

reg_payload = {
    "email": "test@example.com",
    "username": "testuser",
    "password": "strongpassword",
    "full_name": "Test User",
}

login_payload = {"username": "testuser", "password": "strongpassword"}

init_db()
with TestClient(app) as client:
    print("GET / ->", client.get("/").json())
    print("GET /health ->", client.get("/health").json())

    resp = client.post("/auth/register", json=reg_payload)
    print("POST /auth/register ->", resp.status_code, resp.json() if resp.content else None)

    resp = client.post("/auth/login", json=login_payload)
    print("POST /auth/login ->", resp.status_code, resp.json() if resp.content else None)

    if resp.status_code == 200:
        token = resp.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}

        # List documents
        resp = client.get("/documents", headers=headers)
        print("GET /documents ->", resp.status_code, resp.json())

        # Search metadata (empty)
        resp = client.get("/documents/search?company_name=tcs", headers=headers)
        print("GET /documents/search ->", resp.status_code, resp.json())
    else:
        print("Login failed; skipping authenticated routes test")
