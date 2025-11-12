import pytest
from app import create_app
from app.extensions import db

@pytest.fixture
def app():
    app = create_app("development")
    # テストで CSRF 等の影響があるなら設定を上書き
    app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "DISABLE_FORCE_HTTPS": True,  # テストでは HTTPS リダイレクトを無効化
    })
    return app

@pytest.fixture
def client(app):
    return app.test_client()

def test_index_requires_login(client):
    # 未ログインならリダイレクト（302）で /login へ
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 301)

def test_login_page_accessible(client):
    resp = client.get("/login")
    # login ページが表示される（テンプレートがあること）
    assert resp.status_code == 200

def test_admin_worker_requires_login(client):
    resp = client.get("/admin/worker", follow_redirects=False)
    assert resp.status_code in (302, 301)

def test_api_get_prompts(client):
    resp = client.get("/api/get-prompts")
    assert resp.status_code == 200
    assert resp.is_json