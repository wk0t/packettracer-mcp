# Packet Tracer MCP

A local Windows MCP server for Cisco Packet Tracer, with **87 tools** for network configuration, lab files, verification, and scoped desktop controls.

The Python gateway combines the native [pktctl 0.2.2](https://github.com/TantiE100/pktctl/releases/tag/v0.2.2) engine with course-file helpers, working copies, VLSM planning, backups and controls for Cisco windows that are not covered by IPC.

## Features

| Area | Capabilities |
| --- | --- |
| Topology | Create, rename and move devices; inspect interfaces, connect cables and install modules. |
| Configuration | IOS commands and blocks, IPv4/IPv6 hosts, wireless settings and server services. |
| Verification | Command output, ping, traceroute, links, simulation events, saving and reopening networks. |
| Activities | Open `.pka` copies, read instructions and inspect accessible activity status. |
| Course files | Find labs, extract PDF/DOCX/text, preserve originals, calculate VLSM and write reports. |
| Windows interface | Inspect and capture Cisco windows; click, double-click, right-click, type, send keys, drag and scroll. |
| Advanced IPC | Discover the public Cisco API with `describe_ipc` and invoke additional methods with `call_ipc`. |

See the [tool reference](docs/tools.md) and included [workflow skill](SKILL.md).

## Requirements

- Windows x64 and Python 3.12 or later.
- Cisco Packet Tracer **9.0.1**, installed separately. Complete any required Cisco sign-in yourself.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) on PATH or in `%USERPROFILE%\.local\bin`.
- An MCP client with stdio support. Vibe registration is automatic; other clients can use manual configuration.

Java is not required. Packet Tracer and its proprietary SDK are not redistributed.

## Install

Run from PowerShell:

```powershell
git clone https://github.com/wk0t/packettracer-mcp.git
cd packettracer-mcp
.\install.ps1
```

The installer creates an isolated environment, installs pinned dependencies, downloads and verifies the pinned Windows engine, generates local IPC credentials, compiles the Cisco registration file, and registers the MCP server and skill with Vibe. Reinstallation preserves existing credentials. A conflicting MCP configuration is left untouched.

```powershell
# Install without editing Vibe configuration.
.\install.ps1 -SkipVibe

# Use a previously downloaded engine archive.
.\install.ps1 -Archive 'C:\Downloads\pktctl-0.2.2-x86_64-pc-windows-msvc.zip'

# Select a non-default Cisco installation.
.\install.ps1 -PacketTracerHome 'D:\Applications\Cisco Packet Tracer 9.0.1'
```

`-Archive` skips the engine download; Python packages must still be available online or in the uv cache. The archive hash is checked in either mode.

## One-time Cisco registration

1. Open Packet Tracer and select **Extensions → IPC → Configure Apps → Add**.
2. Choose `%USERPROFILE%\.vibe\extensions\packettracer-mcp\registration\vibe-packettracer.pta`.
3. Confirm the application is listed, then close the dialog.
4. In **Extensions → IPC → Options**, enable listening on port `39000`. Remote application access is unnecessary for this local connection.
5. Quit Packet Tracer normally once, then reopen it. Cisco saves the registration when it closes normally.

The installer produces the `.pta`; it does not silently register it inside Cisco. `setup_exapp` can regenerate the file if needed.

## Connect a client

### Vibe

Start a new session after installation:

```text
/mcp packettracer
```

Call `tp_diagnostic` or `status`. A live connection reports `connected: true` and the Packet Tracer version. Vibe prefixes tool names with `packettracer_` and loads the skill from `%USERPROFILE%\.vibe\skills\packettracer-tp\SKILL.md`.

### Other stdio clients

Install with `-SkipVibe`, then adapt this configuration to the client's format. Replace `YOUR_USERNAME` with the installing Windows account.

```json
{
  "mcpServers": {
    "packettracer": {
      "command": "C:\\Users\\YOUR_USERNAME\\.vibe\\extensions\\packettracer-mcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\YOUR_USERNAME\\.vibe\\extensions\\packettracer-mcp\\server.py"]
    }
  }
}
```

Use a startup timeout of at least 20 seconds and a tool timeout of 180 seconds if supported. Client traffic uses stdio; Cisco IPC is a separate local connection.

## Complete a lab with evidence

1. Find files with `tp_lister` and read the assignment with `tp_lire`. Continue from `next_offset` until the document is complete.
2. Create a copy with `tp_preparer`, then pass its `working_file` to `open_network`.
3. Read `activity_instructions`, `list_devices`, `list_ports` and `list_links`. Preserve the assignment's names, addresses and operation order.
4. Apply configuration and inspect `configure_ios.completed`, the applied count and command results. For commands, inspect `finished` and actual output.
5. Verify the required state: interfaces, ARP/MAC/routing tables, ping/traceroute, services or simulation events. Use `fast_forward` when STP, DHCP or routing needs to converge after opening a network.
6. Save with `save_network`, reopen when appropriate, and record results with `tp_rapport`. Distinguish passed, failed and unavailable checks.

Example task:

> Read this assignment and its Packet Tracer activity. Work on a copy, follow the addressing table, complete the requested steps, verify each result with real command output, and save the network and verification report.

## Files and backups

| Default location | Purpose |
| --- | --- |
| `%USERPROFILE%\.vibe\extensions\packettracer-mcp` | Server, environment, engine and local settings. |
| `%USERPROFILE%\Downloads` | Original course documents and activities. |
| `%USERPROFILE%\Documents\PacketTracer-TP` | Working copies, backups, saved networks and reports. |

`tp_preparer` records the source SHA-256 in a manifest. `open_network` automatically copies originals. The gateway saves the current network before an open/new operation clears it, and backs up an existing output before replacing it.

These path protections cover course helpers and wrapped open/save operations. **`call_ipc` and desktop controls remain advanced access** and must follow the same working-copy discipline. The installed `settings.json` and `.pta` contain local authentication material and are excluded from source control. No GitHub token is needed to install or run this server.

## Limitations

- Windows and Packet Tracer 9.0.1 are the validated combination; other releases have not been validated.
- IPC does not expose every feature. Desktop controls provide a fallback but depend on visible windows, correct focus and current coordinates. Interactive sign-in may require personal input.
- Operations that rewrite `.pkt` snapshots, including some advanced physical workspace edits, are refused on `.pka` activities to preserve their container. See [tools](docs/tools.md).
- Author-protected activities may hide scores and checks until the correct author password is supplied. This protection is not bypassed.
- PDF extraction does not perform OCR or interpret diagrams. Pages without extractable text are reported.
- A successful MCP response alone does not prove that a configuration completed or a ping succeeded. Inspect the results.

## Tests and troubleshooting

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

The default suite is offline. Opt-in simulator tests are described in [validation](docs/validation.md). See [configuration and troubleshooting](docs/configuration.md) for connection and file-access problems.

## License and provenance

[MIT License](LICENSE). The native engine is pktctl, maintained by Santi E.; its pinned release, checksum and license appear in [THIRD_PARTY.md](THIRD_PARTY.md). Cisco Packet Tracer is a separate Cisco product. This is an unofficial integration and is not endorsed by Cisco.
