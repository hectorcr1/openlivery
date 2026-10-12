"""Small Composio SDK boundary; the API never exposes project credentials."""

import os

from ...config import get_settings


def configured() -> bool:
    return bool(get_settings().composio_api_key.strip())


def _sdk():
    settings = get_settings()
    if not configured():
        raise RuntimeError("Composio is not configured")
    # The SDK creates this directory on import, including in slim containers.
    os.environ.setdefault("COMPOSIO_CACHE_DIR", str(settings.storage_dir / "composio-cache"))
    from composio import Composio

    return Composio(api_key=settings.composio_api_key)


def client_user_id(agency_id: str, client_id: str) -> str:
    """One durable Composio identity per client; never reuse an agency ID."""
    return f"openlivery:{agency_id}:client:{client_id}"


def list_toolkits(cursor: str | None, limit: int = 40) -> dict:
    response = _sdk().toolkits.list(cursor=cursor, limit=limit, sort_by="usage")
    return {
        "items": [
            {
                "slug": item.slug,
                "name": item.name,
                "description": item.meta.description or "",
                "logo": item.meta.logo or "",
                "categories": [category.name for category in item.meta.categories or []],
                "tools_count": int(item.meta.tools_count or 0),
                "managed_auth": bool(item.composio_managed_auth_schemes),
            }
            for item in response.items
        ],
        "next_cursor": response.next_cursor,
    }


def get_toolkit(slug: str) -> dict:
    item = _sdk().toolkits.get(slug)
    return {
        "slug": item.slug,
        "name": item.name,
        "description": item.meta.description or "",
        "logo": item.meta.logo or "",
        "categories": [category.name for category in item.meta.categories or []],
        "tools_count": int(item.meta.tools_count or 0),
        "managed_auth": bool(item.composio_managed_auth_schemes),
    }


def list_tools(slug: str) -> list[dict]:
    tools = _sdk().tools.get_raw_composio_tools(toolkits=[slug.upper()], limit=1000)
    return [
        {
            "slug": tool.slug,
            "name": tool.name,
            "description": tool.human_description or tool.description,
            "read_only": "readOnlyHint" in tool.tags,
            "destructive": "destructiveHint" in tool.tags,
            # The core MCP executor prefixes each name and providers cap it at 64.
            "supported": len(tool.slug) <= 59,
        }
        for tool in tools
        if not tool.is_deprecated
    ]


def start_authorization(user_id: str, slug: str, callback_url: str) -> tuple[str, str]:
    sdk = _sdk()
    session = sdk.sessions.create(
        user_id=user_id,
        toolkits=[slug],
        manage_connections=False,
        sandbox={"enable": False},
    )
    try:
        return session.session_id, session.authorize(slug, callback_url=callback_url).redirect_url
    except Exception:
        try:
            session.delete()
        except Exception:
            pass
        raise


def active_account(user_id: str, slug: str, account_id: str) -> bool:
    response = _sdk().connected_accounts.list(
        user_ids=[user_id],
        toolkit_slugs=[slug],
        connected_account_ids=[account_id],
        statuses=["ACTIVE"],
        limit=1,
    )
    return any(
        account.id == account_id and account.user_id == user_id and account.toolkit.slug == slug
        for account in response.items
    )


def create_mcp_session(user_id: str, slug: str, account_id: str, tool_slugs: list[str]) -> tuple[str, str, dict[str, str]]:
    from composio import SESSION_PRESET_DIRECT_TOOLS

    session = _sdk().sessions.create(
        user_id=user_id,
        toolkits=[slug],
        tools={slug: {"enable": tool_slugs}},
        connected_accounts={slug: [account_id]},
        session_preset=SESSION_PRESET_DIRECT_TOOLS,
        manage_connections=False,
        sandbox={"enable": False},
        mcp=True,
    )
    return session.session_id, str(session.mcp.url), dict(session.mcp.headers or {})


def delete_session(session_id: str) -> None:
    sdk = _sdk()
    from composio.exceptions import HTTPError, NotFoundError

    try:
        sdk.sessions.use(session_id).delete()
    except (HTTPError, NotFoundError) as exc:
        if getattr(exc, "status_code", 404) != 404:
            raise


def delete_account(account_id: str) -> None:
    sdk = _sdk()
    from composio.exceptions import HTTPError, NotFoundError

    try:
        sdk.connected_accounts.delete(account_id, revoke_on_delete=True)
    except (HTTPError, NotFoundError) as exc:
        if getattr(exc, "status_code", 404) != 404:
            raise
