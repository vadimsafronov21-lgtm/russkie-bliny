import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from backend.app.db import Base, get_db, make_engine
from backend.app.main import create_app
from backend.app.seed import seed


@pytest.fixture
def setup(tmp_path):
    # TEST_DATABASE_URL must point only to a disposable test database (CI).
    url = os.getenv("TEST_DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    if os.getenv("TEST_DATABASE_URL") and not (make_url(url).database or "").endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL должен указывать на отдельную БД с суффиксом _test.")
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        seed(db)
    app = create_app()

    def override():
        with factory() as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = override
    yield app, factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def clients(setup):
    app, _ = setup
    opened = []

    def login(username="point1"):
        client = TestClient(app)
        opened.append(client)
        response = client.post("/api/auth/login", json={"username": username, "password": "Bliny-demo-2026!"})
        assert response.status_code == 200, response.text
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        return client

    yield login
    for client in opened:
        client.close()
