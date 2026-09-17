"""Sheets API v4 registry exposed as independently permissioned tools."""

from dataclasses import dataclass

from ...models import GoogleSheetsConnection
from ..google_sheets import execute_google_sheets_tool
from .specs import ToolSpec


@dataclass(frozen=True)
class GoogleSheetsTool:
    name: str
    description: str
    method: str
    path: str
    read_only: bool = False


def _tool(name: str, description: str, method: str, path: str, read_only: bool = False) -> GoogleSheetsTool:
    return GoogleSheetsTool(f"google_sheets_{name}", description, method, path, read_only)


# Every operation in the official Google Sheets API v4 resource reference.
# `params` and `body` pass through the documented query/body fields unchanged.
GOOGLE_SHEETS_TOOLS = (
    _tool("spreadsheets_batch_update", "Apply one or more spreadsheet updates in a batch.", "POST", "/spreadsheets/{spreadsheet_id}:batchUpdate"),
    _tool("spreadsheets_create", "Create a new spreadsheet.", "POST", "/spreadsheets"),
    _tool("spreadsheets_get", "Get spreadsheet properties, sheets, and optionally cell data.", "GET", "/spreadsheets/{spreadsheet_id}", True),
    _tool("spreadsheets_get_by_data_filter", "Get spreadsheet data selected by data filters.", "POST", "/spreadsheets/{spreadsheet_id}:getByDataFilter", True),
    _tool("developer_metadata_search", "Search spreadsheet developer metadata.", "POST", "/spreadsheets/{spreadsheet_id}/developerMetadata:search", True),
    _tool("sheets_copy_to", "Copy one sheet to another spreadsheet.", "POST", "/spreadsheets/{spreadsheet_id}/sheets/{sheet_id}:copyTo"),
    _tool("values_append", "Append values after the last row of a range.", "POST", "/spreadsheets/{spreadsheet_id}/values/{range}:append"),
    _tool("values_batch_clear", "Clear one or more ranges from a spreadsheet.", "POST", "/spreadsheets/{spreadsheet_id}/values:batchClear"),
    _tool("values_batch_clear_by_data_filter", "Clear values matching data filters.", "POST", "/spreadsheets/{spreadsheet_id}/values:batchClearByDataFilter"),
    _tool("values_batch_get", "Get values from one or more ranges.", "GET", "/spreadsheets/{spreadsheet_id}/values:batchGet", True),
    _tool("values_batch_get_by_data_filter", "Get values matching data filters.", "POST", "/spreadsheets/{spreadsheet_id}/values:batchGetByDataFilter", True),
    _tool("values_batch_update", "Set values in multiple ranges.", "POST", "/spreadsheets/{spreadsheet_id}/values:batchUpdate"),
    _tool("values_batch_update_by_data_filter", "Set values in ranges selected by data filters.", "POST", "/spreadsheets/{spreadsheet_id}/values:batchUpdateByDataFilter"),
    _tool("values_clear", "Clear values from a range.", "POST", "/spreadsheets/{spreadsheet_id}/values/{range}:clear"),
    _tool("values_get", "Get values from a range.", "GET", "/spreadsheets/{spreadsheet_id}/values/{range}", True),
    _tool("values_get_by_data_filter", "Get values from a range selected by data filters.", "POST", "/spreadsheets/{spreadsheet_id}/values/{range}:getByDataFilter", True),
    _tool("values_update", "Set values in a range.", "PUT", "/spreadsheets/{spreadsheet_id}/values/{range}"),
)


def google_sheets_tool_names() -> list[str]:
    return [tool.name for tool in GOOGLE_SHEETS_TOOLS]


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "spreadsheet_id": {"type": "string", "description": "Google Sheets spreadsheet ID from its URL."},
            "sheet_id": {"type": "string", "description": "Numeric sheet ID for the sheets.copyTo operation."},
            "range": {"type": "string", "description": "A1 notation range, such as 'Sheet1!A1:D50'."},
            "params": {"type": "object", "description": "Optional documented query parameters for this Sheets API method."},
            "body": {"type": "object", "description": "Optional documented JSON request body for this Sheets API method."},
        },
    }


def build_google_sheets_specs(db, connection: GoogleSheetsConnection, enabled_names: set[str]) -> list[ToolSpec]:
    specs: list[ToolSpec] = []
    for tool in GOOGLE_SHEETS_TOOLS:
        if tool.name not in enabled_names:
            continue

        async def execute(args: dict, item: GoogleSheetsTool = tool):
            return await execute_google_sheets_tool(db, connection, item.method, item.path, args)

        specs.append(ToolSpec(tool.name, tool.description, _schema(), async_handler=execute))
    return specs
