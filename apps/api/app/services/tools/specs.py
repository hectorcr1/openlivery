"""Build provider-agnostic tool specs from AgentTool rows and dispatch calls.

HTTP tools map 1:1 to a spec; each MCP server row expands into one spec per
cached tool, exposed to the LLM as "{row_name}__{tool_name}". Row names forbid
consecutive underscores, so the "__" separator is unambiguous.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ...models import AgentTool

# Both providers enforce this pattern on tool names.
PROVIDER_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
PATH_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


@dataclass
class ToolSpec:
    name: str            # name exposed to the LLM (prefixed for MCP tools)
    description: str
    input_schema: dict
    tool: AgentTool      # backing row
    mcp_tool_name: str | None = None  # unprefixed name on the MCP server
    executor: Callable[[dict], tuple[str, bool]] | None = None


def path_placeholders(url: str) -> list[str]:
    return PATH_PLACEHOLDER_RE.findall(url)


def _http_input_schema(tool: AgentTool) -> dict:
    properties: dict = {}
    required: list[str] = []
    for name in path_placeholders(tool.url):
        properties[name] = {"type": "string"}
        required.append(name)
    for param in [*(tool.query_params or []), *(tool.body_params or [])]:
        name = param.get("name")
        if not name or name in properties:
            continue
        prop: dict = {"type": param.get("type", "string")}
        if param.get("description"):
            prop["description"] = param["description"]
        properties[name] = prop
        if param.get("required"):
            required.append(name)
    schema: dict = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def build_tool_specs(tools: list[AgentTool]) -> list[ToolSpec]:
    specs: list[ToolSpec] = []
    for tool in tools:
        if tool.type == "http":
            description = tool.description or tool.name
            if tool.prompt_instructions:
                description = f"{description}\n\nWhen to use: {tool.prompt_instructions}"
            specs.append(ToolSpec(tool.name, description, _http_input_schema(tool), tool))
            continue
        for entry in tool.cached_tools or []:
            mcp_name = entry.get("name") or ""
            composite = f"{tool.name}__{mcp_name}"
            if not PROVIDER_NAME_RE.match(composite):
                continue
            specs.append(
                ToolSpec(
                    name=composite,
                    description=entry.get("description") or mcp_name,
                    input_schema=entry.get("input_schema") or {"type": "object", "properties": {}},
                    tool=tool,
                    mcp_tool_name=mcp_name,
                )
            )
    return specs


def build_appointment_specs(db, agent) -> list[ToolSpec]:
    from ...modules.appointments.models import AppointmentSettings
    from ...modules.appointments.tools import execute_appointment_tool
    from sqlalchemy import select

    enabled = db.scalar(select(AppointmentSettings.enabled).where(AppointmentSettings.client_id == agent.client_id))
    if not enabled:
        return []
    definitions = [
        ("appointments_find_availability", "Find available appointment slots. Use before booking or suggesting a time.", {"type": "object", "properties": {"service_id": {"type": "string"}, "date_from": {"type": "string", "description": "ISO datetime"}, "date_to": {"type": "string", "description": "ISO datetime"}, "location_id": {"type": "string"}, "professional_id": {"type": "string"}, "slot_minutes": {"type": "integer"}}, "required": ["service_id", "date_from", "date_to"]}),
        ("appointments_book", "Book an appointment after confirming the selected slot and customer details.", {"type": "object", "properties": {"location_id": {"type": "string"}, "professional_id": {"type": "string"}, "service_id": {"type": "string"}, "starts_at": {"type": "string", "description": "ISO datetime"}, "customer_phone": {"type": "string"}, "customer_name": {"type": "string"}, "customer_email": {"type": "string"}, "notes": {"type": "string"}}, "required": ["location_id", "professional_id", "service_id", "starts_at", "customer_phone", "customer_name"]}),
        ("appointments_get", "Get the details and status of an appointment.", {"type": "object", "properties": {"appointment_id": {"type": "string"}}, "required": ["appointment_id"]}),
        ("appointments_reschedule", "Move an existing appointment to a new available slot.", {"type": "object", "properties": {"appointment_id": {"type": "string"}, "starts_at": {"type": "string", "description": "ISO datetime"}, "location_id": {"type": "string"}, "professional_id": {"type": "string"}, "service_id": {"type": "string"}}, "required": ["appointment_id", "starts_at"]}),
        ("appointments_cancel", "Cancel an existing appointment after the customer confirms.", {"type": "object", "properties": {"appointment_id": {"type": "string"}}, "required": ["appointment_id"]}),
    ]
    return [ToolSpec(name, description, schema, None, executor=lambda args, name=name: execute_appointment_tool(db, agent.client_id, name, args)) for name, description, schema in definitions]


def find_spec(specs: list[ToolSpec], name: str) -> ToolSpec | None:
    for spec in specs:
        if spec.name == name:
            return spec
    return None
