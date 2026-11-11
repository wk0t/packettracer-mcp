"""Opt-in live checks for an installed connector; does not change lab networks."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main(args):
    home = Path(args.home).resolve()
    results = {}
    async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(home/"server.py")])) as (read,write):
        async with ClientSession(read,write) as client:
            await client.initialize()
            definitions = (await client.list_tools()).tools
            assert len(definitions) == 87
            results["tools"] = [t.name for t in definitions]
            async def call(name, arguments):
                response = await client.call_tool(name,arguments)
                assert not response.isError, response
                return response.structuredContent or json.loads(next(c.text for c in response.content if c.type=="text"))
            results["diagnostic"] = await call("tp_diagnostic",{})
            assert results["diagnostic"]["packet_tracer"]["connected"]
            results["windows"] = await call("ui_windows",{})
            window = results["windows"]["windows"][0]
            results["inspection"] = await call("ui_inspect",{"window_id":window["window_id"],"max_nodes":20})
            assert results["inspection"]["inspection"]["nodes"]
            results["ipc"] = await call("call_ipc",{"from":"network","steps":[{"method":"getDeviceCount"}]})
            assert results["ipc"]["value"] >= 0
            blocked = await client.call_tool("ui_click",{"window_id":-1,"x":0,"y":0})
            assert blocked.isError
            results["invalid_window_rejected"] = True
            if args.regenerate_registration:
                results["registration"] = await call("setup_exapp",{})
                assert Path(results["registration"]["pta"]).is_file()
            results["final_status"] = await call("status",{})
            assert results["final_status"]["connected"] is True
    output = Path(__file__).resolve().parents[1]/"validation-installation.json"
    output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SMOKE OK: 87 tools, IPC connected, Cisco windows inspected, invalid handle rejected")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--home",default=str(Path.home()/".vibe/extensions/packettracer-mcp"))
    parser.add_argument("--regenerate-registration",action="store_true")
    asyncio.run(main(parser.parse_args()))
