"""앱 진입점 테스트: 상태 확인 API 와 React 빌드 결과 서빙."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

INDEX_HTML = '<div id="root"></div>'


@pytest.fixture
def dist(tmp_path):
    """index.html 과 assets/app.js 만 있는 가짜 빌드 폴더."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return dist


def test_health_works_without_frontend_build(tmp_path):
    """빌드 폴더가 없어도(개발 모드) API 는 응답한다."""
    client = TestClient(create_app(tmp_path / "missing"))
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_root_is_404_without_frontend_build(tmp_path):
    """빌드 폴더가 없으면 화면 경로는 등록되지 않는다."""
    client = TestClient(create_app(tmp_path / "missing"))
    assert client.get("/").status_code == 404


def test_root_serves_index_html(dist):
    """첫 화면은 index.html 이다."""
    res = TestClient(create_app(dist)).get("/")
    assert res.status_code == 200
    assert res.text == INDEX_HTML


def test_static_asset_is_served(dist):
    """빌드된 JS 파일은 그대로 내보낸다."""
    res = TestClient(create_app(dist)).get("/assets/app.js")
    assert res.status_code == 200
    assert res.text == "console.log(1)"


def test_client_route_falls_back_to_index_html(dist):
    """화면 주소로 바로 들어오거나 새로고침해도 index.html 을 준다."""
    res = TestClient(create_app(dist)).get("/claims/RB-00006")
    assert res.status_code == 200
    assert res.text == INDEX_HTML


def test_unknown_api_path_is_404_not_index(dist):
    """없는 API 주소는 index.html 이 아니라 404 다."""
    res = TestClient(create_app(dist)).get("/api/nope")
    assert res.status_code == 404
    assert res.json() == {"detail": "Not Found"}


def test_path_outside_dist_is_not_served(dist):
    """../ 로 빌드 폴더 밖 파일을 요청해도 내용이 새지 않는다."""
    (dist.parent / "secret.txt").write_text("SECRET", encoding="utf-8")
    res = TestClient(create_app(dist)).get("/assets/..%2F..%2Fsecret.txt")
    assert "SECRET" not in res.text
