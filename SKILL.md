---
name: packettracer-tp
description: Complete and verify Cisco Packet Tracer network labs using the packettracer MCP server, course documents, working copies, IOS commands, simulation and scoped Windows controls.
---

# Packet Tracer lab workflow

Use the `packettracer` MCP server for local Cisco Packet Tracer labs. Vibe uses the `packettracer_` prefix; `/mcp packettracer` lists the tools. The server exposes 72 native tools, seven course helpers and eight Windows controls.

## Establish the assignment and working copy

1. Check `tp_diagnostic` or `status`. If Cisco is closed, use `tp_demarrer`, wait for it and check status again.
2. Find the supplied assignment and `.pkt`/`.pka` with `tp_lister`. Read the complete document with `tp_lire`, continuing from `next_offset`. Preserve required names, addresses, modes and operation order. Inspect diagrams separately; report pages without extractable text.
3. Call `tp_preparer`, then `open_network` with its `working_file`. Keep originals in the configured downloads root and results in the workspace.
4. Read `activity_instructions`, `list_devices`, `list_ports` and `list_links`. Compare actual topology with the assignment before making changes. Ask only for a missing detail that changes the result.

## Configure and verify

- Prefer dedicated tools and read their schemas rather than guessing arguments or device models.
- With `configure_ios`, check `completed`, `applied`, `total` and individual results. Stop at rejected commands, diagnose and correct before continuing.
- With `run_cli` and `run_host_command`, inspect `finished`, any status field and the actual output. MCP transport success alone is not a successful network check.
- Follow the addressing table. `tp_vlsm` can verify IPv4 allocations; do not replace an assigned plan without reason.
- Allow STP, DHCP or routing to converge with `fast_forward` after opening or modifying a network, then repeat relevant checks.
- Verify the lab's requirements using interfaces, VLANs, MAC/ARP tables, routes, neighbors, ping/traceroute, services or simulation events as appropriate.
- Use `describe_ipc` before `call_ipc` for additional API methods. Advanced calls can write files and change state beyond helper path guards; keep them inside the working-copy scope.

## Use the desktop fallback when needed

Call `ui_windows`, then `ui_inspect` and `ui_screenshot` with a returned identifier. Perform one action using `ui_click`, `ui_type_text`, `ui_press_keys`, `ui_drag` or `ui_scroll`, then inspect again. Right-click and double-click are available through `ui_click`.

Coordinates are relative to the selected window. Reobserve after unexpected changes and confirm the correct field and focus immediately before typing. Select an enabled modal rather than a blocked parent. The tools verify the configured Cisco executable at every call.

Use desktop interaction on the activity copy. Report personal sign-in or protected-dialog requirements instead of inventing a successful result.

## Save and report evidence

- Preserve `.pka` activity containers. Operations that rewrite `.pkt` snapshots are refused on `.pka`; use a separate `.pkt` or the appropriate visible Cisco controls on the activity copy.
- Do not guess author passwords or bypass activity locks. State when a score or check is unavailable.
- Save with `save_network`; reopen and verify persistence when appropriate.
- Use `tp_rapport` to record requirements, applied steps, actual outputs, passed/failed checks, limitations and produced files.
- Claim successful configuration, connectivity, scores and saves only when supported by observed results. Keep failed and untested items distinct.
