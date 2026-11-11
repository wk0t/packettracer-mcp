# Configuration and troubleshooting

The default installation is `%LOCALAPPDATA%\PacketTracerMCP`, with `%USERPROFILE%\AppData\Local\PacketTracerMCP` as the fallback when `LOCALAPPDATA` is unset. Use `install.ps1 -InstallDir 'D:\Tools\PacketTracerMCP'` to choose another directory. It contains the gateway, helpers, `vendor/` engine, isolated `.venv/`, generated `registration/packettracer-mcp.pta`, `settings.json`, `mcp-config.json`, and the optional `skills/packettracer-tp/SKILL.md`.

## Connect a local stdio MCP client

Any MCP client that can launch a local stdio server can use this gateway. The installer writes `mcp-config.json` as a connection fragment and does not modify any client's settings. Manually merge the `packettracer` entry into your client's MCP configuration, preserving other servers. Adapt the fragment to the client's schema when it does not use an `mcpServers` JSON object. Use absolute paths; environment-variable expansion in client configuration is not universal.

The generated command uses the installation's `.venv\Scripts\python.exe`, the absolute `server.py` path, and `--settings` with the absolute `settings.json` path. For a direct launch from a source checkout or an environment with the requirements installed:

```powershell
python .\server.py --settings 'D:\Tools\PacketTracerMCP\settings.json'
```

If the native engine is stored separately, add `--runtime-dir <directory>` to select its runtime directory.

The server uses stdin and stdout for MCP messages. Launch it through your MCP client for tool use; a shell launch alone is not an interactive command interface. Remote HTTP-only clients need a separate local stdio bridge, which is not provided.

The MCP initialization response provides workflow instructions. A `SKILL.md` loader is optional; if your client supports one, add the installed `skills/packettracer-tp/SKILL.md` using that client's mechanism. Tool prefixes and display namespaces vary by client. This repository uses the unprefixed tool names advertised by the server.

## Runtime settings

| Setting | Purpose |
| --- | --- |
| `app_id` | Reverse-domain identifier registered with Cisco; preserved on reinstallation. |
| `secret` | Locally generated random IPC credential. Keep it outside repositories and reports. |
| `address` | Local Cisco endpoint, normally `127.0.0.1:39000`. |
| `downloads` | Permitted source directory for course files. |
| `workspace` | Separate root for working files, backups and reports. It must not overlap downloads. |
| `packet_tracer_home` | Cisco directory containing `bin/PacketTracer.exe` and `bin/meta.exe`. |

Settings are selected in this order: `--settings <path>`, `PACKETTRACER_MCP_SETTINGS`, `settings.json` beside the server, then `settings.json` in the default installation directory. The installer discovers Cisco from an existing setting or Program Files; `-PacketTracerHome` selects an explicit directory. Changing the identifier or secret requires regenerating and registering the matching `.pta`.

```text
MCP client
  └─ stdio → Python gateway
                ├─ stdio → pktctl → local Cisco IPC
                ├─ course files → permitted roots
                └─ Windows controls → verified Cisco windows
```

The MCP process can initialize before Cisco is ready. `status` checks the actual simulator connection.

| Symptom | Check |
| --- | --- |
| Server missing | Check that the connection fragment was merged into the intended client's configuration, verify absolute executable and settings paths, and restart or reload the MCP connection. |
| Tool name not found | Refresh the client's tool discovery and use its displayed namespace or prefix. |
| Cisco unreachable | Open Cisco and verify IPC listening and the configured address. Another instance may use another port. |
| Application identifier rejected | Register the matching `.pta`, then quit Cisco normally once. |
| Missing privilege | Regenerate with `setup_exapp` and register the resulting file again. |
| Gateway file access denied | Put originals under the downloads root, create a working copy, and write inside the workspace. |
| Partial configuration | Check `completed`, `applied`, per-command results, `finished` and actual output. |
| Ping fails after opening | Let protocols converge with `fast_forward`, then verify addressing, interface state and ping again. |
| Activity score unavailable | Evaluation may require its author's password; do not infer a score. |
| Desktop input rejected | Refresh windows and select the enabled modal; inspect current focus and coordinates. |
| Black screenshot | Restore the window or use `screenshot` with `view: "logical"`. |
| Conflicting MCP entry | Review the existing `packettracer` entry before manually merging the generated fragment; keep other servers intact. |

Generated credentials, registration files, personal labs and validation reports are excluded by `.gitignore`.
