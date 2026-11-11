"""Standard MCP negotiation and tools from independently named clients."""
import asyncio
from contextlib import suppress
import json
from pathlib import Path
import sys

import pytest
from mcp import ClientSession, types
from mcp.shared.memory import create_client_server_memory_streams

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import Gateway, LOCAL_TOOLS, UI_TOOLS, build_server, INSTRUCTIONS, CONNECTOR_VERSION


class ProtocolEngine:
    async def call_tool(self, name, arguments, **kwargs):
        if name == "call_ipc":
            data = {"value":""}
        elif name == "status":
            data = {"connected":False,"problem":"simulator intentionally offline"}
        elif name == "configure_ios":
            data = {"device":"R1","completed":False,"applied":0,"total":1,"saved":False,
                    "results":[{"command":"invalid","status":"invalid"}]}
        elif name == "screenshot":
            return types.CallToolResult(content=[types.ImageContent(type="image",mimeType="image/png",data="cG5n")])
        else:
            return types.CallToolResult(isError=True,content=[types.TextContent(type="text",text="simulated native error")])
        return types.CallToolResult(content=[types.TextContent(type="text",text=json.dumps(data))],structuredContent=data)


def gateway(tmp_path):
    result = Gateway({"downloads":str(tmp_path/"downloads"),"workspace":str(tmp_path/"work")},ProtocolEngine())
    own_names = {t.name for t in LOCAL_TOOLS+UI_TOOLS}
    catalog = json.loads((Path(__file__).resolve().parents[1]/"docs/tool-schemas.json").read_text(encoding="utf-8"))
    result.native = {t["name"]:types.Tool.model_validate(t) for t in catalog["tools"] if t["name"] not in own_names}
    return result


@pytest.mark.parametrize("client_name",["desktop-mcp-client","terminal-mcp-client"])
def test_standard_mcp_clients_negotiate_discover_and_use_same_tools(tmp_path,client_name):
    async def exercise():
        server = build_server(gateway(tmp_path))
        async with create_client_server_memory_streams() as (client_streams,server_streams):
            task = asyncio.create_task(server.run(*server_streams,server.create_initialization_options()))
            try:
                async with ClientSession(*client_streams,client_info=types.Implementation(name=client_name,version="1.0")) as client:
                    initialized = await client.initialize()
                    assert initialized.serverInfo.name == "packettracer"
                    assert initialized.serverInfo.version == CONNECTOR_VERSION
                    assert initialized.instructions == INSTRUCTIONS
                    tools = (await client.list_tools()).tools
                    assert len(tools) == 87
                    assert all(not t.name.startswith(client_name) for t in tools)
                    assert {t.name for t in tools} >= {"tp_vlsm","run_cli","ui_windows"}
                    plan = await client.call_tool("tp_vlsm",{"network":"192.0.2.0/24","lans":[{"name":"LAN","hosts":30}]})
                    assert not plan.isError
                    assert plan.structuredContent["subnets"][0]["network"] == "192.0.2.0/27"
                    status = await client.call_tool("status",{})
                    assert not status.isError and status.structuredContent["connected"] is False
                    partial = await client.call_tool("configure_ios",{"device":"R1","commands":["invalid"]})
                    assert partial.structuredContent["completed"] is False
                    image = await client.call_tool("screenshot",{"view":"logical"})
                    assert image.content[0].type == "image" and image.content[0].data == "cG5n"
                    invalid = await client.call_tool("tp_vlsm",{"network":"invalid","lans":[]})
                    assert invalid.isError
                    malformed = await client.call_tool("tp_vlsm",{})
                    assert malformed.isError
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
    asyncio.run(exercise())
