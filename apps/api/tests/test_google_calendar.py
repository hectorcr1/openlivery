from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.models import GoogleCalendarConnection
from app.security import encrypt_secret
from app.services import google_calendar
from app.services.tools.google_calendar_specs import GOOGLE_CALENDAR_TOOLS, build_google_calendar_specs
from app.services.tools.google_sheets_specs import GOOGLE_SHEETS_TOOLS, build_google_sheets_specs


def _agent(client: TestClient, customer_id: str, name: str) -> str:
    return client.post("/api/agents", json={"client_id": customer_id, "name": name, "is_active": True}).json()["id"]


def _connected_calendar(agent_id: str):
    from app.models import Agent
    from conftest import TestingSession

    with TestingSession() as db:
        agent = db.get(Agent, agent_id)
        db.add(GoogleCalendarConnection(
            agency_id=agent.agency_id, client_id=agent.client_id,
            encrypted_access_token=encrypt_secret("access"), encrypted_refresh_token=encrypt_secret("refresh"),
            status="connected",
        ))
        db.commit()


def test_calendar_tools_require_connection_and_are_scoped_to_each_agent(authenticated_client: TestClient):
    client = authenticated_client
    first_customer = client.post("/api/clients", json={"name": "First calendar client"}).json()
    second_customer = client.post("/api/clients", json={"name": "Second calendar client"}).json()
    first_agent = _agent(client, first_customer["id"], "First")
    second_agent = _agent(client, first_customer["id"], "Second")
    other_agent = _agent(client, second_customer["id"], "Other")

    # No client connection means no agent can activate Calendar functions.
    attempted = client.put(f"/api/agents/{first_agent}/integrations/google-calendar/tools", json={"enabled_tools": ["google_calendar_events_insert"]})
    assert attempted.status_code == 400

    _connected_calendar(first_agent)
    listed = client.get(f"/api/agents/{first_agent}/integrations/google-calendar/tools")
    assert listed.status_code == 200
    assert len(listed.json()) == len(GOOGLE_CALENDAR_TOOLS)
    assert all(item["enabled"] is False for item in listed.json())

    updated = client.put(f"/api/agents/{first_agent}/integrations/google-calendar/tools", json={
        "enabled_tools": ["google_calendar_events_list", "google_calendar_events_insert"],
    })
    assert updated.status_code == 200
    assert set(updated.json()["enabled_tools"]) == {"google_calendar_events_list", "google_calendar_events_insert"}
    assert client.get(f"/api/agents/{second_agent}/integrations/google-calendar").json()["enabled_tools"] == []

    # A connection for one client cannot unlock another client's agent.
    forbidden = client.put(f"/api/agents/{other_agent}/integrations/google-calendar/tools", json={"enabled_tools": ["google_calendar_events_list"]})
    assert forbidden.status_code == 400


def test_calendar_specs_only_expose_the_permitted_functions():
    permitted = {"google_calendar_events_list", "google_calendar_events_insert"}
    specs = build_google_calendar_specs(None, None, permitted)
    assert [spec.name for spec in specs] == ["google_calendar_events_insert", "google_calendar_events_list"]
    assert all(spec.async_handler is not None for spec in specs)


def test_callback_url_accepts_an_origin_or_a_complete_callback_url(monkeypatch):
    settings = SimpleNamespace(
        google_public_url="https://openlivery.example/api/google/oauth/callback",
        frontend_url="http://localhost:3000",
    )
    monkeypatch.setattr(google_calendar, "get_settings", lambda: settings)
    assert google_calendar.callback_url() == "https://openlivery.example/api/google/oauth/callback"

    settings.google_public_url = "https://openlivery.example"
    assert google_calendar.callback_url() == "https://openlivery.example/api/google/oauth/callback"


def test_sheets_specs_expose_only_the_permitted_functions():
    permitted = {"google_sheets_values_get", "google_sheets_values_update"}
    specs = build_google_sheets_specs(None, None, permitted)
    assert len(GOOGLE_SHEETS_TOOLS) == 17
    assert [spec.name for spec in specs] == ["google_sheets_values_get", "google_sheets_values_update"]
    assert all(spec.async_handler is not None for spec in specs)
