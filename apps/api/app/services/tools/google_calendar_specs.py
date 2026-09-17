"""Calendar v3 method registry exposed as independently permissioned tools."""

from dataclasses import dataclass

from ...models import GoogleCalendarConnection
from ..google_calendar import execute_google_calendar_tool
from .specs import ToolSpec


@dataclass(frozen=True)
class GoogleCalendarTool:
    name: str
    description: str
    method: str
    path: str
    read_only: bool = False


def _tool(name: str, description: str, method: str, path: str, read_only: bool = False) -> GoogleCalendarTool:
    return GoogleCalendarTool(f"google_calendar_{name}", description, method, path, read_only)


# This mirrors every resource method in the official Calendar API v3 reference.
# All methods share a compact generic schema: identifiers are explicit while
# `params` and `body` map directly to that method's documented query/body fields.
GOOGLE_CALENDAR_TOOLS = (
    _tool("acl_delete", "Delete an access control rule from a calendar.", "DELETE", "/calendars/{calendar_id}/acl/{rule_id}"),
    _tool("acl_get", "Get one access control rule from a calendar.", "GET", "/calendars/{calendar_id}/acl/{rule_id}", True),
    _tool("acl_insert", "Create an access control rule on a calendar.", "POST", "/calendars/{calendar_id}/acl"),
    _tool("acl_list", "List access control rules for a calendar.", "GET", "/calendars/{calendar_id}/acl", True),
    _tool("acl_patch", "Partially update an access control rule.", "PATCH", "/calendars/{calendar_id}/acl/{rule_id}"),
    _tool("acl_update", "Replace an access control rule.", "PUT", "/calendars/{calendar_id}/acl/{rule_id}"),
    _tool("acl_watch", "Create a push notification channel for ACL changes.", "POST", "/calendars/{calendar_id}/acl/watch"),
    _tool("calendar_list_delete", "Remove a calendar from the user's calendar list.", "DELETE", "/users/me/calendarList/{calendar_id}"),
    _tool("calendar_list_get", "Get a calendar from the user's calendar list.", "GET", "/users/me/calendarList/{calendar_id}", True),
    _tool("calendar_list_insert", "Add an existing calendar to the user's calendar list.", "POST", "/users/me/calendarList"),
    _tool("calendar_list_list", "List every calendar available to the connected Google account.", "GET", "/users/me/calendarList", True),
    _tool("calendar_list_patch", "Partially update a calendar list entry.", "PATCH", "/users/me/calendarList/{calendar_id}"),
    _tool("calendar_list_update", "Replace a calendar list entry.", "PUT", "/users/me/calendarList/{calendar_id}"),
    _tool("calendar_list_watch", "Create a push notification channel for calendar-list changes.", "POST", "/users/me/calendarList/watch"),
    _tool("calendars_clear", "Delete all events from a primary or secondary calendar.", "POST", "/calendars/{calendar_id}/clear"),
    _tool("calendars_delete", "Delete a secondary calendar.", "DELETE", "/calendars/{calendar_id}"),
    _tool("calendars_get", "Get metadata for a calendar.", "GET", "/calendars/{calendar_id}", True),
    _tool("calendars_insert", "Create a secondary calendar.", "POST", "/calendars"),
    _tool("calendars_patch", "Partially update calendar metadata.", "PATCH", "/calendars/{calendar_id}"),
    _tool("calendars_update", "Replace calendar metadata.", "PUT", "/calendars/{calendar_id}"),
    _tool("channels_stop", "Stop a Calendar API push-notification channel.", "POST", "/channels/stop"),
    _tool("colors_get", "Get the color definitions available in Google Calendar.", "GET", "/colors", True),
    _tool("events_delete", "Delete or cancel an event.", "DELETE", "/calendars/{calendar_id}/events/{event_id}"),
    _tool("events_get", "Get one event by its Google Calendar event ID.", "GET", "/calendars/{calendar_id}/events/{event_id}", True),
    _tool("events_import", "Import an event with an iCalendar UID.", "POST", "/calendars/{calendar_id}/events/import"),
    _tool("events_insert", "Create an event or appointment on a calendar.", "POST", "/calendars/{calendar_id}/events"),
    _tool("events_instances", "List the occurrences of a recurring event.", "GET", "/calendars/{calendar_id}/events/{event_id}/instances", True),
    _tool("events_list", "List or search events on a calendar.", "GET", "/calendars/{calendar_id}/events", True),
    _tool("events_move", "Move an event to another calendar. Include destination in params.destination.", "POST", "/calendars/{calendar_id}/events/{event_id}/move"),
    _tool("events_patch", "Partially update an event or appointment.", "PATCH", "/calendars/{calendar_id}/events/{event_id}"),
    _tool("events_quick_add", "Create an event from a natural-language text. Include text in params.text.", "POST", "/calendars/{calendar_id}/events/quickAdd"),
    _tool("events_update", "Replace an event or appointment.", "PUT", "/calendars/{calendar_id}/events/{event_id}"),
    _tool("events_watch", "Create a push notification channel for event changes.", "POST", "/calendars/{calendar_id}/events/watch"),
    _tool("freebusy_query", "Query busy time ranges across one or more calendars.", "POST", "/freeBusy", True),
    _tool("settings_get", "Get one Calendar setting for the connected account.", "GET", "/users/me/settings/{setting}", True),
    _tool("settings_list", "List Calendar settings for the connected account.", "GET", "/users/me/settings", True),
    _tool("settings_watch", "Create a push notification channel for settings changes.", "POST", "/users/me/settings/watch"),
)


def google_calendar_tool_names() -> list[str]:
    return [tool.name for tool in GOOGLE_CALENDAR_TOOLS]


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "calendar_id": {"type": "string", "description": "Calendar ID. Use 'primary' when appropriate."},
            "event_id": {"type": "string", "description": "Google Calendar event ID."},
            "rule_id": {"type": "string", "description": "Google Calendar ACL rule ID."},
            "setting": {"type": "string", "description": "Google Calendar setting ID."},
            "params": {"type": "object", "description": "Optional documented query parameters for this Calendar API method."},
            "body": {"type": "object", "description": "Optional documented JSON request body for this Calendar API method."},
        },
    }


def build_google_calendar_specs(db, connection: GoogleCalendarConnection, enabled_names: set[str]) -> list[ToolSpec]:
    specs: list[ToolSpec] = []
    for tool in GOOGLE_CALENDAR_TOOLS:
        if tool.name not in enabled_names:
            continue
        async def execute(args: dict, item: GoogleCalendarTool = tool):
            return await execute_google_calendar_tool(db, connection, item.method, item.path, args)
        specs.append(ToolSpec(tool.name, tool.description, _schema(), async_handler=execute))
    return specs
