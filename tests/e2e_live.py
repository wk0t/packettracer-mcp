"""Exercise the installed MCP against a live Packet Tracer; creates test copies."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main(args):
    report = {"started_at":datetime.now(timezone.utc).isoformat(), "checks":[]}
    home = Path(args.home).resolve()
    settings = json.loads((home / "settings.json").read_text(encoding="utf-8-sig"))
    workspace = Path(settings["workspace"]) / "validation-connecteur"
    workspace.mkdir(parents=True, exist_ok=True)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(home / "server.py"), "--settings", str(home / "settings.json")],
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as client:
            await client.initialize()
            tools = (await client.list_tools()).tools
            assert len(tools) == 87
            report["tools"] = [t.name for t in tools]

            async def call(tool_name, **arguments):
                result = await client.call_tool(tool_name, arguments)
                texts = "\n".join(c.text for c in result.content if c.type == "text")
                data = result.structuredContent
                if data is None:
                    try:
                        data = json.loads(texts)
                    except (ValueError, TypeError):
                        data = {"text":texts}
                report["checks"].append({"tool":tool_name,"arguments":arguments,"is_error":bool(result.isError),"result":data})
                Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                assert not result.isError, (tool_name, texts)
                print(tool_name, json.dumps(data, ensure_ascii=False)[:250], flush=True)
                return data

            diagnostic = await call("tp_diagnostic")
            assert diagnostic["packet_tracer"]["connected"] is True
            windows = await call("ui_windows")
            assert windows["windows"], "No Cisco window available for the UI fallback"
            inspected = await call("ui_inspect", window_id=windows["windows"][0]["window_id"], max_nodes=20)
            assert inspected["inspection"]["nodes"], "Cisco UI inspection returned no controls"
            await call("new_network")
            for model, name, x, y in [("2911","R1",200,150),("2960-24TT","S1",200,300),("PC-PT","PC1",100,450),("PC-PT","PC2",300,450)]:
                await call("add_device", model=model, name=name, x=x, y=y)
            await call("list_devices")
            await call("list_ports", device="R1")
            for a, pa, b, pb in [("R1","GigabitEthernet0/0","S1","GigabitEthernet0/1"),("PC1","FastEthernet0","S1","FastEthernet0/1"),("PC2","FastEthernet0","S1","FastEthernet0/2")]:
                await call("connect", device_a=a, port_a=pa, device_b=b, port_b=pb, cable="straight")
            await call("list_links")
            configured = await call("configure_ios",device="R1",commands=["hostname R1","interface GigabitEthernet0/0","ip address 192.0.2.1 255.255.255.0","no shutdown"],save=True)
            assert configured["completed"] is True
            for device, ip in [("PC1","192.0.2.10"),("PC2","192.0.2.20")]:
                await call("configure_host",device=device,ip=ip,mask="255.255.255.0",gateway="192.0.2.1")
            await call("fast_forward")
            cli = await call("run_cli",device="R1",command="show ip interface brief",mode="enable")
            assert "192.0.2.1" in cli["output"] and cli["finished"]
            ping = await call("run_host_command",device="PC1",command="ping 192.0.2.20",timeout_secs=20)
            if not re.search(r"(?:Lost\s*=\s*0|0%\s*loss)", ping.get("output",""), re.I):
                ping = await call("run_host_command",device="PC1",command="ping 192.0.2.20",timeout_secs=20)
            assert ping["finished"] and re.search(r"(?:Lost\s*=\s*0|0%\s*loss)", ping["output"], re.I)
            await call("simulation_mode",on=True)
            await call("add_pdu",source="PC1",destination="PC2")
            await call("simulation_step",action="forward",times=20)
            events = await call("list_simulation_events",protocols=["ICMP","ARP"],include_decisions=True,limit=50)
            assert events.get("matching",0) > 0, "Simulation returned no matching events"
            await call("simulation_mode",on=False)
            path = str(workspace / "reseau-verifie.pkt")
            saved = await call("save_network",path=path)
            assert saved["bytes"] > 0 and Path(path).is_file()
            await call("open_network",path=path)
            await call("fast_forward")
            ping = await call("run_host_command",device="PC1",command="ping 192.0.2.20",timeout_secs=20)
            assert ping["finished"] and "Reply from 192.0.2.20" in ping["output"]
            await call("list_locations")
            await call("show_workspace",view="physical")
            await call("show_workspace",view="logical")
            await call("screenshot",view="logical",save_to=str(workspace / "topology.png"))
            if args.activity:
                selected = Path(args.activity).resolve()
                digest = hashlib.sha256(selected.read_bytes()).hexdigest()
                prepared = await call("tp_preparer",path=str(selected))
                await call("open_network",path=prepared["working_file"])
                instructions = await call("activity_instructions")
                assert len(instructions["text"]) > 50
                activity = await call("activity_status")
                assert activity["is_activity"] is True
                await call("list_devices")
                await call("save_network",path=str(Path(prepared["workspace"]) / "verified-activity.pka"))
                assert hashlib.sha256(selected.read_bytes()).hexdigest() == digest
                report["original_unchanged"] = True
            if args.assignment:
                text = await call("tp_lire",path=str(Path(args.assignment).resolve()))
                assert len(text["text"]) > 50
            # Leave the demonstration network open for inspection.
            await call("open_network",path=path)
            await call("fast_forward")
            report["completed"] = True
            report["completed_at"] = datetime.now(timezone.utc).isoformat()
            Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
            print("E2E OK",len(report["checks"]),"calls",flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--home",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--activity",help="Optional .pka inside the configured source roots.")
    parser.add_argument("--assignment",help="Optional course document inside the configured source roots.")
    asyncio.run(main(parser.parse_args()))
