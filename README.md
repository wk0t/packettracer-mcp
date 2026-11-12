# Packet Tracer MCP

A local MCP server with **87 tools** for Cisco Packet Tracer: build networks, apply configuration, verify results and work with course activities.

Validated on **Windows x64 with Cisco Packet Tracer 9.0.1**. Connect using any MCP client that supports local stdio servers.

## First run

### 1. Install

Install Cisco Packet Tracer 9.0.1 and [uv](https://docs.astral.sh/uv/getting-started/installation/), then run in PowerShell:

```powershell
git clone https://github.com/wk0t/packettracer-mcp.git
cd packettracer-mcp
.\install.ps1
```

The default location is `%LOCALAPPDATA%\PacketTracerMCP`. The installer prepares Python, pinned dependencies, the verified engine and local configuration. It preserves existing IPC credentials and leaves client settings for you to merge.

See [installation](docs/installation.md) for ZIP download, prerequisite checks, custom directories, cached archives and the expected output.

### 2. Register in Cisco

In Packet Tracer, select **Extensions → IPC → Configure Apps → Add** and choose `<installation directory>\registration\packettracer-mcp.pta`. Enable listening on port `39000` under **Extensions → IPC → Options**. Quit Packet Tracer normally once to save the registration, then reopen it and complete any Cisco sign-in.

This registration is needed once per set of IPC credentials. [Detailed steps](docs/installation.md#register-in-cisco).

### 3. Connect and verify

Open `<installation directory>\mcp-config.json`. Manually merge its `packettracer` entry into your client's local MCP configuration, preserving other servers, then reload the connection. Adapt the fragment if your client uses another configuration schema.

Discover the tools: expect **87 tools**. Call `status`: expect `connected: true` and the Packet Tracer version. Clients may display their own tool prefixes; use the discovered names. The [installation check](docs/validation.md#check-an-installed-connector) can verify this directly from PowerShell.

Try a small first task:

> Check Packet Tracer's connection, then list the devices and links in the open network. Do not make changes.

## Capabilities

| Area | Examples |
| --- | --- |
| Topology | Create and move devices, connect cables, inspect ports and install modules. |
| Configuration | Apply IOS commands, IPv4/IPv6 addressing, wireless settings and server services. |
| Verification | Inspect command output, ping, traceroute, routing state and simulation events. |
| Activities | Read `.pka` instructions and accessible assessment results; save working copies. |
| Course files | Read PDF, DOCX and text assignments; plan VLSM; create backups and reports. |
| Cisco interface | Inspect and capture Cisco windows; click, type, send keys, drag and scroll. |
| Advanced access | Explore the Cisco IPC API with `describe_ipc`, then use `call_ipc`. |

See the [tool reference](docs/tools.md) for names, arguments and limitations. Workflow instructions are supplied during MCP initialization; the optional [workflow skill](SKILL.md) is also included.

## Complete a lab

1. Find the assignment with `tp_lister`; read it with `tp_lire`, continuing from `next_offset` until complete.
2. Use `tp_preparer` to create a copy, then pass its `working_file` to `open_network`.
3. Inspect the instructions, devices, ports and links before configuring. Preserve the required names, addressing and operation order.
4. Apply changes and inspect `completed`, applied counts and command output. Use `fast_forward` when protocols need to converge, then verify the required connectivity and services.
5. Save with `save_network` and record evidence with `tp_rapport`. Keep passed, failed and unavailable checks distinct.

Originals default to `%USERPROFILE%\Downloads`; working copies, backups and reports default to `%USERPROFILE%\Documents\PacketTracer-TP`. Wrapped open/new operations back up the current network, and wrapped saves back up existing outputs. Advanced IPC and desktop actions still require the same working-copy discipline.

## Limits and help

- Windows x64 and Packet Tracer 9.0.1 are the validated combination.
- Some features require visible Cisco windows and correct focus. Personal sign-in may require input.
- Some operations that rewrite `.pkt` snapshots are unavailable on `.pka` activities. Protected assessments may require the author's password.
- Document extraction does not perform OCR or interpret diagrams. A successful tool response alone does not prove a network check passed; inspect its results.

See [configuration and troubleshooting](docs/configuration.md) or [validation and tests](docs/validation.md). Keep generated `settings.json` and `.pta` credentials private and outside source control.

## License

[MIT](LICENSE). The native engine is [pktctl 0.2.2](https://github.com/TantiE100/pktctl/releases/tag/v0.2.2), maintained by Santi E.; its checksum and license are documented in [THIRD_PARTY.md](THIRD_PARTY.md). Cisco Packet Tracer is installed separately and is not redistributed. This is an unofficial integration and is not endorsed by Cisco.
