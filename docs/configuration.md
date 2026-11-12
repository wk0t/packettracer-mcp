# Configuration and troubleshooting

For installation, Cisco registration and the MCP connection fragment, see [installation](installation.md). Use the [installed connector check](validation.md#check-an-installed-connector) to distinguish installation problems from an unavailable simulator.

## Runtime settings

The installer writes `settings.json` in the installation directory. It preserves existing IPC credentials on reinstallation.

| Setting | Purpose |
| --- | --- |
| `app_id` | Reverse-domain identifier registered with Cisco. |
| `secret` | Locally generated IPC credential. Keep it outside repositories and reports. |
| `address` | Local Cisco endpoint; default `127.0.0.1:39000`. |
| `downloads` | Permitted source directory for course files; default `%USERPROFILE%\Downloads`. |
| `workspace` | Root for working copies, backups and reports; default `%USERPROFILE%\Documents\PacketTracer-TP`. It must not overlap `downloads`. |
| `packet_tracer_home` | Cisco directory containing `bin\PacketTracer.exe` and `bin\meta.exe`. |

Settings are selected in this order:

1. `--settings <path>`.
2. `PACKETTRACER_MCP_SETTINGS`.
3. `settings.json` beside `server.py`.
4. `settings.json` in the default installation directory.

The generated client fragment always supplies an explicit settings path. After changing settings, restart the MCP connection. Changes to `app_id` or `secret` also require regenerating and registering the matching `.pta`; changes to `address` must match Cisco's IPC listener.

The installer discovers Cisco from an existing setting or Program Files. Use `-PacketTracerHome` to choose another installation. For a source checkout with dependencies already installed, the equivalent server command is:

```powershell
python .\server.py --settings 'D:\Tools\PacketTracerMCP\settings.json'
```

Add `--runtime-dir <directory>` when the native engine is stored separately. The process uses stdin and stdout for MCP messages and should be launched by a local stdio MCP client.

## Files and backups

Keep original course documents and `.pkt`/`.pka` files in `downloads`. Use `tp_preparer` to make a working copy in `workspace`, then open its returned `working_file`. Its manifest records the source SHA-256. Wrapped `open_network` also copies originals automatically.

The gateway backs up the current network before an open/new operation clears it, and backs up an existing output before replacing it. These protections apply to course helpers and wrapped open/save operations. Advanced `call_ipc` and desktop actions must follow the same working-copy discipline.

Generated credentials, registration files, personal labs and `validation*.json` reports are excluded by `.gitignore`.

## Troubleshooting

The MCP server can initialize while Cisco is closed or unregistered. Successful discovery confirms the client connection; `status` confirms the separate Cisco IPC connection.

| Symptom | Action |
| --- | --- |
| Install prerequisite error | Run `.\install.ps1 -Check` from the source directory. Check uv and the Cisco installation path; pass `-PacketTracerHome` for a custom path. |
| Server missing or startup fails | Run the [offline installation check](validation.md#check-an-installed-connector). Check the merged client entry, absolute paths and `--settings` argument, then reload the connection. |
| Tool name not found | Refresh discovery and use the client's displayed name or prefix. Expect 87 tools. |
| Cisco unreachable | Open Cisco, complete sign-in, and check IPC listening and the configured address. Another Cisco instance may use another port. |
| Application identifier rejected | Add the matching `.pta` in Cisco, then quit Cisco normally once and reopen. |
| Missing privilege | Regenerate with `setup_exapp`, register the resulting file again, and exit Cisco normally once. |
| Gateway file access denied | Put originals under `downloads`, create a working copy, and write inside `workspace`. |
| Partial configuration | Inspect `completed`, `applied`, per-command results, `finished` and actual output before continuing. |
| Ping fails after opening | Use `fast_forward` to allow convergence, then verify addressing, interface state and ping again. |
| Activity score unavailable | Evaluation may require the author's password; report the check as unavailable. |
| Desktop input rejected | Refresh `ui_windows`, select the enabled modal and inspect current focus and coordinates. |
| Black screenshot | Restore the Cisco window or use `screenshot` with `view: "logical"`. |
| Conflicting client entry | Review the existing `packettracer` entry and manually merge the generated fragment while preserving other servers. |
