# Configuration and troubleshooting

The default installation is `%USERPROFILE%\.vibe\extensions\packettracer-mcp`. It contains the gateway, helpers, `vendor/` engine, isolated `.venv/`, generated `registration/` and `settings.json`.

| Setting | Purpose |
| --- | --- |
| `app_id` | Reverse-domain identifier registered with Cisco; preserved on reinstallation. |
| `secret` | Locally generated random IPC credential. Keep it outside repositories and reports. |
| `address` | Local Cisco endpoint, normally `127.0.0.1:39000`. |
| `downloads` | Permitted source directory for course files. |
| `workspace` | Separate root for working files, backups and reports. It must not overlap downloads. |
| `packet_tracer_home` | Cisco directory containing `bin/PacketTracer.exe` and `bin/meta.exe`. |

`PACKETTRACER_MCP_SETTINGS` selects another settings file. The installer discovers Cisco from an existing setting or Program Files; `-PacketTracerHome` selects an explicit directory. Changing the identifier or secret requires regenerating and registering the matching `.pta`.

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
| Server missing | Start a new client session and check absolute executable paths; use `/mcp packettracer` in Vibe. |
| Cisco unreachable | Open Cisco and verify IPC listening and the configured address. Another instance may use another port. |
| Application identifier rejected | Register the matching `.pta`, then quit Cisco normally once. |
| Missing privilege | Regenerate with `setup_exapp` and register the resulting file again. |
| Gateway file access denied | Put originals under the downloads root, create a working copy, and write inside the workspace. |
| Partial configuration | Check `completed`, `applied`, per-command results, `finished` and actual output. |
| Ping fails after opening | Let protocols converge with `fast_forward`, then verify addressing, interface state and ping again. |
| Activity score unavailable | Evaluation may require its author's password; do not infer a score. |
| Desktop input rejected | Refresh windows and select the enabled modal; inspect current focus and coordinates. |
| Black screenshot | Restore the window or use `screenshot` with `view: "logical"`. |
| Conflicting MCP entry | Existing configuration is preserved; review it or use `-SkipVibe`. |

Generated credentials, registration files, personal labs and validation reports are excluded by `.gitignore`.
