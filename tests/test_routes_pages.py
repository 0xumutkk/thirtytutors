"""Page shells for the logged-in home flow. Who gets sent where happens in
the browser (localStorage.tutorProfileId), so this pins the markup those
redirects depend on rather than the redirects themselves.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from thirtytutors import routes_pages


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(routes_pages.router)
    return TestClient(app)


def test_home_page_renders_the_dashboard(client):
    res = client.get("/home")
    assert res.status_code == 200
    assert 'id="homeWrap"' in res.text
    assert "/UI/scripts/home.js" in res.text


def test_top_bar_home_link_points_at_the_dashboard(client):
    assert 'id="homeLink" href="/home"' in client.get("/home").text


def test_landing_page_sends_logged_in_profiles_home_before_rendering(client):
    html = client.get("/landing").text
    assert html.index("window.location.replace('/home')") < html.index("</head>")
