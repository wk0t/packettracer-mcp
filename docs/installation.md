# Installation

## Requirements

- Windows x64 and Cisco Packet Tracer **9.0.1**, installed separately.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) on PATH or at `%USERPROFILE%\.local\bin\uv.exe`.
- An MCP client that can launch a local stdio server.
- Internet access for the default install. A cached engine archive and cached Python packages can be used as described below.

The PowerShell installer uses an existing 64-bit Python 3.12+ or prepares Python 3.12 through uv. Java and a GitHub token are unnecessary. Complete Cisco sign-in in Packet Tracer when requested.

## Get the source

Clone the repository and open its directory in PowerShell:

```powershell
git clone https://github.com/wk0t/packettracer-mcp.git
cd packettracer-mcp
```

Alternatively, download the repository using **Code → Download ZIP**, extract it, and open PowerShell in the extracted directory containing `install.ps1`. Git is only needed for cloning.

## Check prerequisites

```powershell
.\install.ps1 -Check
```

This read-only check reports prerequisites before installation. It does not install the connector, generate credentials or register anything in Cisco. Resolve any reported prerequisite errors, then run the install. For a non-default Cisco location, pass `-PacketTracerHome` to both commands.

If the check cannot find Python, run `uv python install 3.12` and retry. A normal install prepares missing Python automatically.

## Install

```powershell
.\install.ps1
```

If PowerShell blocks local scripts, use `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1` for this invocation. It does not change the saved execution policy.

The default directory is `%LOCALAPPDATA%\PacketTracerMCP`, falling back to `%USERPROFILE%\AppData\Local\PacketTracerMCP` when `LOCALAPPDATA` is unset. The installer creates an isolated Python environment, installs pinned dependencies, downloads and verifies the pinned Windows engine, generates IPC credentials and compiles a Cisco registration file. Reinstallation preserves existing credentials.

| Option | Use |
| --- | --- |
| `-InstallDir 'D:\Tools\PacketTracerMCP'` | Select the installation directory. Use this same directory for later checks and reinstalls. |
| `-PacketTracerHome 'D:\Applications\Cisco Packet Tracer 9.0.1'` | Select the Cisco directory containing `bin\PacketTracer.exe` and `bin\meta.exe`. |
| `-Archive 'C:\Downloads\pktctl-0.2.2-x86_64-pc-windows-msvc.zip'` | Use a previously downloaded engine archive; its SHA-256 is still verified. |
| `-Check` | Check prerequisites without installing the connector. |

Options can be combined:

```powershell
.\install.ps1 -InstallDir 'D:\Tools\PacketTracerMCP' `
  -PacketTracerHome 'D:\Applications\Cisco Packet Tracer 9.0.1'
```

`-Archive` skips the engine download. Python and packages must still be available online or in the uv cache; this option alone does not make an installation fully offline.

### Expected result

Progress messages identify the installation phases. A successful run ends with a JSON summary containing the installation directory, engine version, connection fragment, optional skill, registration file and workspace paths.

| Installed path | Purpose |
| --- | --- |
| `.venv\Scripts\python.exe` | Python interpreter used by the MCP client. |
| `server.py`, `doctor.py`, helpers and `vendor\` | Gateway, installation check and native engine. |
| `settings.json` | Local paths and IPC credentials. |
| `registration\packettracer-mcp.pta` | Application registration to add in Cisco. |
| `mcp-config.json` | Connection fragment to merge into the MCP client. |
| `skills\packettracer-tp\SKILL.md` | Optional workflow for clients supporting skills. |

The installer does not edit any client's configuration or register the `.pta` in Cisco. Keep `settings.json` and `.pta` private.

## Register in Cisco

1. Open Packet Tracer and select **Extensions → IPC → Configure Apps → Add**.
2. Select `<installation directory>\registration\packettracer-mcp.pta`.
3. Confirm the application is listed and close the dialog.
4. Under **Extensions → IPC → Options**, enable listening on port `39000`. Remote application access is unnecessary for the default local connection.
5. **Quit Packet Tracer normally once**, then reopen it. Cisco saves the registration on normal exit.

Repeat registration if the IPC identifier or secret changes. The `setup_exapp` tool can regenerate the `.pta` from the current settings; add the regenerated file in Cisco and exit normally again.

## Connect the MCP client

Open `<installation directory>\mcp-config.json` and manually merge its `packettracer` entry into the client's MCP server configuration. Preserve other server entries and settings. Client configuration locations and schemas vary; adapt the generated command and arguments to its local stdio format.

For a client using an `mcpServers` object, the generated fragment has this shape. Replace `YOUR_USERNAME` and adjust custom installation paths. Use absolute paths because clients do not all expand environment variables.

```json
{
  "mcpServers": {
    "packettracer": {
      "command": "C:\\Users\\YOUR_USERNAME\\AppData\\Local\\PacketTracerMCP\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\YOUR_USERNAME\\AppData\\Local\\PacketTracerMCP\\server.py",
        "--settings",
        "C:\\Users\\YOUR_USERNAME\\AppData\\Local\\PacketTracerMCP\\settings.json"
      ]
    }
  }
}
```

Use a startup timeout of at least 20 seconds and a tool timeout of 180 seconds if the client supports those settings. Reload or restart the MCP connection, discover **87 tools**, and call `status`. A ready simulator reports `connected: true` and its version. Names may include a client-specific prefix.

For a small first task, inspect the connection, devices and links without changing the open network. Use the [installed connector check](validation.md#check-an-installed-connector) if discovery or connection fails, then consult [troubleshooting](configuration.md#troubleshooting).

The server supplies workflow instructions during MCP initialization. Clients with a skill loader can optionally load `skills\packettracer-tp\SKILL.md`. A shell launch of `server.py` waits for MCP messages; use an MCP client for tool calls. Clients restricted to remote HTTP servers require a separate local stdio bridge, which is not included.
