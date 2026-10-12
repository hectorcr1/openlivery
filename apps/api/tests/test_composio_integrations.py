"""The catalog is shared by an agency; credentials and sessions are not."""

from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient

from app.extensions.composio_integrations import router as integration_router
from app.extensions.composio_integrations import service


TOOLKIT = {
    "slug": "airtable",
    "name": "Airtable",
    "description": "Organize records",
    "logo": "https://example.test/logo.svg",
    "categories": ["Productivity"],
    "tools_count": 2,
    "managed_auth": True,
}
TOOLS = [
    {"slug": "AIRTABLE_LIST_RECORDS", "name": "List records", "description": "Read rows", "read_only": True, "destructive": False, "supported": True},
    {"slug": "AIRTABLE_DELETE_RECORD", "name": "Delete record", "description": "Remove a row", "read_only": False, "destructive": True, "supported": True},
]


def _agent(client: TestClient, client_id: str, name: str) -> str:
    response = client.post("/api/agents", json={
        "client_id": client_id,
        "provider": "openrouter",
        "model": "openai/gpt-5.6-luna",
        "name": name,
        "instructions": "",
        "personality": "",
        "is_active": True,
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _client(client: TestClient, name: str) -> str:
    response = client.post("/api/clients", json={"name": name, "is_active": True})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _mock_provider(monkeypatch):
    monkeypatch.setattr(service, "configured", lambda: True)
    monkeypatch.setattr(service, "get_toolkit", lambda slug: TOOLKIT)
    monkeypatch.setattr(service, "list_tools", lambda slug: TOOLS)
    monkeypatch.setattr(service, "active_account", lambda user_id, slug, account_id: account_id == "ca_client_a")
    monkeypatch.setattr(service, "create_mcp_session", lambda user_id, slug, account_id, selected: (
        "session_client_a", "https://backend.composio.dev/mcp/session_client_a", {"x-api-key": "server-only-key"},
    ))
    monkeypatch.setattr(service, "delete_session", lambda session_id: None)
    monkeypatch.setattr(service, "delete_account", lambda account_id: None)
    monkeypatch.setattr(integration_router, "discover_mcp_tools", AsyncMock(return_value=[
        {"name": tool["slug"], "description": tool["description"], "input_schema": {"type": "object", "properties": {}}}
        for tool in TOOLS
    ]))


def _connect(client: TestClient, monkeypatch, agent_id: str) -> None:
    callback = {}

    def start(user_id: str, slug: str, callback_url: str) -> tuple[str, str]:
        callback["url"] = callback_url
        return "authorization_session", "https://connect.composio.dev/link/test"

    monkeypatch.setattr(service, "start_authorization", start)
    response = client.post(f"/api/composio/agents/{agent_id}/connect/airtable")
    assert response.status_code == 200, response.text
    state = parse_qs(urlparse(callback["url"]).query)["state"][0]
    finished = client.get(
        "/api/composio/oauth/callback",
        params={"state": state, "status": "success", "connected_account_id": "ca_client_a"},
        follow_redirects=False,
    )
    assert finished.status_code == 303, finished.text
    # A replay cannot connect another account using the same OAuth attempt.
    assert client.get("/api/composio/oauth/callback", params={"state": state}).status_code == 400


def test_client_connection_cannot_be_used_by_another_client(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _mock_provider(monkeypatch)
    first = _client(client, "Customer A")
    second = _client(client, "Customer B")
    agent_a = _agent(client, first, "Agent A")
    agent_b = _agent(client, second, "Agent B")

    assert client.post("/api/composio/install", json={"slug": "airtable"}).status_code == 201
    _connect(client, monkeypatch, agent_a)

    state_a = client.get(f"/api/composio/agents/{agent_a}").json()["items"][0]
    state_b = client.get(f"/api/composio/agents/{agent_b}").json()["items"][0]
    assert state_a["connected"] is True
    assert state_b["connected"] is False
    denied = client.put(f"/api/composio/agents/{agent_b}/assign/airtable", json={"tool_slugs": ["AIRTABLE_LIST_RECORDS"]})
    assert denied.status_code == 409

    assigned = client.put(f"/api/composio/agents/{agent_a}/assign/airtable", json={"tool_slugs": ["AIRTABLE_LIST_RECORDS"]})
    assert assigned.status_code == 200, assigned.text
    tools = client.get(f"/api/agents/{agent_a}/tools").json()
    assert len(tools) == 1
    assert tools[0]["enabled_tools"] == ["AIRTABLE_LIST_RECORDS"]
    assert tools[0]["has_headers"] is True
    assert "server-only-key" not in str(tools)
    assert client.get(f"/api/agents/{agent_b}/tools").json() == []

    # Moving an assigned agent would otherwise expose the first client's tools.
    assert client.patch(f"/api/agents/{agent_a}", json={"client_id": second}).status_code == 409
    assert client.delete(f"/api/agents/{agent_a}").status_code == 409


def test_assign_only_known_actions_and_disconnect_removes_all_client_agents(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _mock_provider(monkeypatch)
    client_id = _client(client, "Customer A")
    agent_a = _agent(client, client_id, "Agent A")
    agent_b = _agent(client, client_id, "Agent B")
    client.post("/api/composio/install", json={"slug": "airtable"})
    _connect(client, monkeypatch, agent_a)

    assert client.put(f"/api/composio/agents/{agent_a}/assign/airtable", json={"tool_slugs": ["NOT_IN_CATALOG"]}).status_code == 422
    assert client.put(f"/api/composio/agents/{agent_a}/assign/airtable", json={"tool_slugs": ["AIRTABLE_LIST_RECORDS"]}).status_code == 200
    assert client.put(f"/api/composio/agents/{agent_b}/assign/airtable", json={"tool_slugs": ["AIRTABLE_DELETE_RECORD"]}).status_code == 200

    assert client.delete(f"/api/composio/agents/{agent_a}/connect/airtable").status_code == 204
    assert client.get(f"/api/agents/{agent_a}/tools").json() == []
    assert client.get(f"/api/agents/{agent_b}/tools").json() == []
    assert client.get(f"/api/composio/agents/{agent_a}").json()["items"][0]["connected"] is False


def test_deleting_client_revokes_composio_account_and_sessions(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _mock_provider(monkeypatch)
    client_id = _client(client, "Customer A")
    agent_id = _agent(client, client_id, "Agent A")
    client.post("/api/composio/install", json={"slug": "airtable"})
    _connect(client, monkeypatch, agent_id)
    assert client.put(f"/api/composio/agents/{agent_id}/assign/airtable", json={"tool_slugs": ["AIRTABLE_LIST_RECORDS"]}).status_code == 200

    delete_session = Mock()
    delete_account = Mock()
    monkeypatch.setattr(service, "delete_session", delete_session)
    monkeypatch.setattr(service, "delete_account", delete_account)
    assert client.delete(f"/api/clients/{client_id}").status_code == 204
    delete_session.assert_called_once_with("session_client_a")
    delete_account.assert_called_once_with("ca_client_a")


def test_failed_discovery_removes_new_remote_session(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _mock_provider(monkeypatch)
    client_id = _client(client, "Customer A")
    agent_id = _agent(client, client_id, "Agent A")
    client.post("/api/composio/install", json={"slug": "airtable"})
    _connect(client, monkeypatch, agent_id)

    delete_session = Mock()
    monkeypatch.setattr(service, "delete_session", delete_session)
    monkeypatch.setattr(integration_router, "discover_mcp_tools", AsyncMock(return_value=[]))
    response = client.put(f"/api/composio/agents/{agent_id}/assign/airtable", json={"tool_slugs": ["AIRTABLE_LIST_RECORDS"]})
    assert response.status_code == 502
    delete_session.assert_called_once_with("session_client_a")
    assert client.get(f"/api/agents/{agent_id}/tools").json() == []


def test_pending_authorization_is_closed_when_agent_is_deleted(authenticated_client: TestClient, monkeypatch):
    client = authenticated_client
    _mock_provider(monkeypatch)
    client_id = _client(client, "Customer A")
    agent_id = _agent(client, client_id, "Agent A")
    client.post("/api/composio/install", json={"slug": "airtable"})
    monkeypatch.setattr(service, "start_authorization", lambda user_id, slug, callback: (
        "authorization_session", "https://connect.composio.dev/link/test",
    ))
    delete_session = Mock()
    monkeypatch.setattr(service, "delete_session", delete_session)

    assert client.post(f"/api/composio/agents/{agent_id}/connect/airtable").status_code == 200
    assert client.delete(f"/api/agents/{agent_id}").status_code == 204
    delete_session.assert_called_once_with("authorization_session")
