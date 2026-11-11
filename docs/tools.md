# Tool reference

The gateway exposes 87 tools: 72 native tools, seven course helpers and eight Windows controls. Tool names below are unprefixed; Vibe adds `packettracer_`.

The complete input schemas are available in [tool-schemas.json](tool-schemas.json). Required arguments are listed below; consult the schema for optional fields, enums and return descriptions.

## Course files and connection

| Tool | Required arguments | Purpose |
| --- | --- | --- |
| `tp_demarrer` | None | Open Packet Tracer installed on this PC, then call status to verify the connection. |
| `tp_diagnostic` | None | Check connector status, engine version, directories and the live connection to Packet Tracer. |
| `tp_lire` | `path` | Read PDF/Word/text instructions, including tables. Paginate using offset; report scanned PDFs. |
| `tp_lister` | None | Find .pka/.pkt labs and PDF/Word instructions in Downloads and working copies. |
| `tp_preparer` | `path` | Copy a .pka/.pkt into a unique working directory; return working_file to open. Preserve the original and its SHA256. |
| `tp_rapport` | `path`, `content` | Save a Markdown report of steps, commands, evidence, results and limitations in the working directory. |
| `tp_vlsm` | `network`, `lans` | Calculate and validate a non-overlapping IPv4 VLSM plan (LAN convention: exclude network/broadcast addresses, minimum /30). |

## Windows controls

| Tool | Required arguments | Purpose |
| --- | --- | --- |
| `ui_click` | `window_id`, `x`, `y` | Click in Cisco after a recent observation, using relative coordinates. Right-click and double-click are available. |
| `ui_drag` | `window_id`, `from_x`, `from_y`, `to_x`, `to_y` | Drag an element between two points in the same Cisco window, such as a module or physical object. Observe before and after. |
| `ui_inspect` | `window_id` | Read the elements and focus of a Cisco window before interacting. Repeat after each action. |
| `ui_press_keys` | `window_id`, `keys` | Send a simple key chord to Cisco: CTRL+SHIFT+C, ENTER, TAB, ESC, ALT+F4... Return the new state. |
| `ui_screenshot` | `window_id` | View a verified Cisco window as a PNG for features without an API. Reject black captures; do not capture the desktop. |
| `ui_scroll` | `window_id`, `x`, `y`, `ticks` | Scroll a Cisco area under point x,y; positive ticks scroll up, negative ticks scroll down. |
| `ui_type_text` | `window_id`, `text` | Type literal text in Cisco. Check the field and focus immediately beforehand. Return the state after typing. |
| `ui_windows` | None | List Cisco Packet Tracer windows, including dialogs. Use the returned window_id values. |

## Native network and activity tools

| Tool | Required arguments | Purpose |
| --- | --- | --- |
| `activity_instructions` | None | Read a page of the open activity's instructions, as text and as HTML. |
| `activity_status` | None | Progress of the open activity (.pka): percentage complete, score, assessment items and points, instruction pages, time elapsed or left. For a plain network it only says it is not an activity. |
| `add_device` | `model` | Add a device to the logical workspace by model name (see list_models), optionally naming it and placing it at x/y. Routers and switches boot immediately. Returns the device as Packet Tracer now shows it. |
| `add_location` | `kind` | Create a place in the physical workspace: a `city`, a `building`, a `wiring_closet`, or furniture to arrange devices on (`rack`, `table`, `shelf`, `cable_pegboard`, `container`), with an optional name and position. Cities and closets use Packet Tracer's own buttons; the rest are written into the network file and come back with the temporary copy Packet Tracer now has open, so save with save_network to keep them. |
| `add_module` | `device`, `slot`, `module` | Install a module (for example HWIC-2T for serial ports) in an empty slot. The device is powered off, the module inserted and the device powered back on, exactly like real hardware, so unsaved configuration is lost. Returns the ports the module added. |
| `add_note` | `x`, `y`, `text` | Write a text note on the logical canvas, for example to label a subnet or a VLAN. Returns the note with its id. |
| `add_pdu` | `source`, `destination` | Send a simple PDU (ICMP echo) from one device to another, like the Add Simple PDU button. In Realtime mode it goes at once; in Simulation mode it waits for simulation_step. |
| `add_server_user` | `device`, `service`, `username`, `password` | Add an FTP account (with permissions such as RWDNL) or an email account to a server. |
| `arrange_devices` | `location` | Lay devices out inside a room, building, rack or table of the physical workspace, moving in the ones that are somewhere else. Positions are percentages of the room, which is how Packet Tracer draws them: leave them out for an even grid, set `columns` and `margin_percent` to shape it, or give exact `spots` like [[20, 30], [60, 30]]. |
| `browse_web` | `device`, `url` | Open a URL in the Web Browser of a PC, laptop or server, like typing it and pressing Go, and return the page Packet Tracer served: its status (ok, timeout, host_not_found, ...), the server's address, the HTML and the text. Names are resolved through the host's DNS server. |
| `call_ipc` | `from` | Call any Packet Tracer IPC method: start at a root or an object uuid and chain `steps`, like `network` -> getDevice("R1") -> getPower(). Every step is checked against the official API before anything is sent, with exact argument types; objects come back as a class and uuid you can start the next call from. Prefer the dedicated tools when one fits; this reaches everything else, including changes, so read describe_ipc first. |
| `check_activity` | None | Run the open activity's connectivity tests and return them with the current completion and score, like Check Results. |
| `configure_access_point` | `device`, `ssid` | Set the SSID, security (open, wep, wpa_psk, wpa2_psk), key and SSID broadcast of an access point or wireless router. Clients keep their current association until connect_wireless reconnects them. |
| `configure_dhcp_server` | `device` | Configure the DHCP service of a server: switch it on and create or update pools (gateway, DNS, start address, mask, maximum users). Existing pools with the same name are updated. |
| `configure_dns_server` | `device` | Switch a server's DNS service on and add A, CNAME or NS records. |
| `configure_email` | `device`, `name`, `email`, `username`, `password`, `incoming_server`, `outgoing_server` | Set up the Email app of a PC, laptop or server: display name, address, user name, password and the incoming (POP3) and outgoing (SMTP) servers. Returns the account as Packet Tracer now has it. |
| `configure_host` | `device` | Set the IPv4 configuration of a PC, laptop or server: either DHCP, or a static ip and mask with optional gateway and DNS. Catches classic mistakes (invalid mask, host address equal to the network or broadcast, gateway outside the subnet) before touching Packet Tracer. |
| `configure_host_ipv6` | `device` | Set the IPv6 configuration of a PC, laptop or server, like the IPv6 part of IP Configuration: `static` with an address such as 2001:db8:10::20/64, `auto` for SLAAC, or `off`; optional gateway (usually the router's link-local fe80::1) and DNS. Returns the addresses Packet Tracer now has on the port. |
| `configure_ios` | `device`, `commands` | Apply a block of IOS configuration commands to a router or switch, as if typed after `configure terminal`: the first command enters global configuration and the rest follow the prompt, so `interface ...` sub-modes work. Stops at the first command IOS rejects, always leaves configuration mode, and runs `write memory` when `save` is true. |
| `connect` | `device_a`, `port_a`, `device_b`, `port_b` | Cable two ports together. Both ports must exist and be free. With the default `auto` cable pktctl picks serial, straight or cross the way the CCNA rules do; pass `cable` to force fiber, rollover, console, etc. |
| `connect_wireless` | `device`, `ssid` | Connect a laptop, PC or other client with a wireless card to a network: SSID, security and key, plus DHCP or a static address. Packet Tracer only associates when a network is loaded, so pktctl takes the network as bytes, sets the client's current profile, opens the result as a temporary copy (your own file is not written) and reports whether it associated and with which access point. |
| `describe_ipc` | None | Explore Packet Tracer's complete IPC API (every class, method, argument and enum of the official framework). Give `search` to find methods by keyword, `class` to list everything an object offers, `enum` to read accepted values, or nothing for the list of roots. Use it before call_ipc for anything the dedicated tools do not cover. |
| `disconnect` | `device`, `port` | Remove the cable plugged into a port. |
| `draw` | `x`, `y` | Draw on the logical canvas: a `circle` (centre and radius) around a subnet or group, a `rectangle` (two corners) to frame an area, or a `line` to mark a boundary. `color` is the outline (`red`, `blue`, `green`, ... or `#rrggbb`); `fill` fills circles and rectangles. The drawing is written into the network file, which Packet Tracer reopens from a temporary copy; save with a path to keep it. Returns the id `remove_drawing` takes. |
| `fast_forward` | None | Press Realtime mode's Fast Forward Time button: timers jump ahead so spanning tree converges, DHCP leases arrive and routing protocols settle at once instead of after 30 seconds or more. Call it after cabling or configuring, before testing connectivity. |
| `get_preferences` | None | Read Packet Tracer's preferences: port labels, link lights, device labels, auto cabling, animation, sound, device dialog tabs, toolbars and more. |
| `host_files` | `device` | Work with the text files of a PC, laptop or server, the ones its Text Editor opens and `dir` lists: `list`, `read`, `write` (creates or replaces) or `delete` a file in C:\. |
| `list_devices` | None | List every device in the open network with its model, kind (router, switch, pc, ...) and canvas position. Use the names to target devices in other tools. |
| `list_drawings` | None | List the circles, rectangles and lines drawn on the logical canvas with their ids and centres. |
| `list_links` | None | List every cable in the network with both endpoints and the cable type. |
| `list_locations` | None | List the physical workspace: Intercity, cities, buildings, wiring closets and racks, each with its path, position and the devices placed in it. |
| `list_models` | None | List the device models this Packet Tracer can create, straight from its hardware catalog, optionally filtered by kind (router, switch, pc, server, access_point, ...). Set include_modules to also list slot modules such as HWIC-2T or NIM-2T, or give a module kind (interface_card, pt_laptop_module, ...) to list only those modules. |
| `list_notes` | None | List the text notes on the logical canvas with their ids and positions. Port labels drawn at cable ends are left out unless include_port_labels is true. |
| `list_ports` | `device` | List a device's ports with their state, IPv4 address when they have one, and what each port is connected to. Use it to pick free ports before connect. |
| `list_server_services` | `device` | List the services of a server (DHCP, DNS, HTTP, HTTPS, FTP, SMTP, POP3, NTP, Syslog, TFTP) and whether each one is on. |
| `list_simulation_events` | None | Read the simulation event list: where each PDU was, when, which protocol, and whether it was accepted or dropped. With include_decisions, also Packet Tracer's per-layer explanation of each step, the same text as the PDU Details window. |
| `list_slots` | `device` | List a device's module slots (path, the kind of module each accepts, what is installed) and the module models the device supports. |
| `move_device` | `name`, `x`, `y` | Move a device to a new position on the logical canvas. |
| `move_to_location` | `into` | Move a device, or a whole location such as a wiring closet, to another place in the physical workspace, for example a switch into `Home City/Corporate Office/Main Wiring Closet`. Devices moved into a wiring closet land on its rack or table. |
| `network_description` | None | Read the open file's description (the Description button in Packet Tracer), or replace it with `text`. |
| `new_network` | None | Start an empty network. Unsaved changes are discarded unless `save_current_to` gives a path to save them first. |
| `open_network` | `path` | Open a .pkt or .pka file. Unsaved changes in the current network are discarded unless `save_current_to` gives a path to save them first. Never shows a dialog. |
| `power_cycle_all` | None | Power cycle every device that is on, like the Power Cycle Devices button but without its confirmation dialog: every device reloads and unsaved configuration on every router and switch is lost. Returns the devices cycled. |
| `receive_email` | `device` | Press Receive in the Email app: download the account's new mail over POP3 and return it. Like a real POP3 client, the mail is removed from the server; Packet Tracer does not expose the app's inbox, so keep what this returns. |
| `remove_device` | `name` | Delete a device and all of its links from the network. |
| `remove_drawing` | `id` | Remove a circle, rectangle or line from the logical canvas by id. |
| `remove_location` | `path` | Delete a city, building, wiring closet or rack with everything inside it. Devices must be moved out first (move_to_location); the power units Packet Tracer puts in racks go with it. Packet Tracer has no call for this, so pktctl edits the network as bytes and opens the result as a temporary copy; save with save_network and a path to keep the change. |
| `remove_module` | `device`, `slot` | Remove the module in a slot, power cycling the device like add_module. Returns the ports that disappeared with it. |
| `remove_note` | `id` | Delete a note from the logical canvas by id. |
| `rename_device` | `name`, `new_name` | Rename a device. The new name must not be taken by another device. |
| `rename_location` | `path`, `name` | Rename a city, building, wiring closet or other location. Packet Tracer has no call for this, so pktctl takes the network as bytes, edits them and opens the result as a temporary copy; your own file is not written, save with save_network and a path to keep the change. |
| `reset_activity` | None | Reset the open activity to its initial network, discarding the work done in it. |
| `run_cli` | `device`, `command` | Type one IOS command at the console of a router or switch and return its output, including commands that take time such as ping or traceroute. `status` tells whether IOS accepted the command. A command still running after `timeout_secs` is stopped with Ctrl+Shift+6 and comes back with `finished: false` and the output so far. When IOS asks something ([confirm], [yes/no], Password:) the reply carries `question` and the console keeps waiting: answer with another run_cli in mode `current`, an empty command for Enter. |
| `run_host_command` | `device`, `command` | Run a command in the Command Prompt of a PC, laptop or server (ping, ipconfig, tracert, nslookup, arp -a) and return its output. Waits until the command finishes; a command still running after `timeout_secs` (ping -t) is stopped with Ctrl+C and comes back with `finished: false` and the output so far. |
| `save_network` | None | Save the open network as a .pkt file, without any dialog. Give an absolute path, or omit it to save over the file already open. |
| `screenshot` | None | Capture Packet Tracer as a PNG image: the logical workspace rendered by Packet Tracer (default), the physical workspace (`view: physical`, which switches views for a moment), or the window as it is with any dialog open (`view: window`). Optionally also write it to an absolute .png path. |
| `send_email` | `device`, `to`, `subject`, `body` | Send an email from the account set up with configure_email and wait for the SMTP server's answer. A recipient the server does not know comes back later as a delivery failure in receive_email. |
| `set_background` | `image` | Paper a physical location (a city, building, room or rack) with a background image, or the logical workspace when no location is given. Takes one of Packet Tracer's own backgrounds (grid_10x10, grid_25x25, grid_50x50, grid_100x100, city, building, intercity, container) or the absolute path of an image; an empty image clears it. |
| `set_host_firewall` | `device` | Use the Firewall and IPv6 Firewall apps of a PC, laptop or server: switch each one on or off, add rules (permit or deny ip, icmp, tcp or udp, by remote address and port) and remove them. Returns both switches and the rules in the order the firewall evaluates them. |
| `set_power` | `device`, `on` | Switch a device on or off. Switching a router or switch off and on reloads it: configuration that was not saved with write memory is lost. IOS devices come back ready at the prompt. |
| `set_preferences` | `values` | Change Packet Tracer preferences by name, for example `{ "values": { "show_port_labels": true } }`. Returns every preference afterwards. |
| `set_server_service` | `device`, `service`, `enabled` | Switch one service of a server on or off, as in its Services tab. |
| `set_web_page` | `device`, `url`, `contents` | Write a page of a server's HTTP service, for example index.html. |
| `setup_exapp` | None | Create the Packet Tracer app registration file (.pta) for pktctl's configured app id and secret, using Packet Tracer's own `meta` tool, and return the one-time steps to register it. Works while Packet Tracer still rejects pktctl. |
| `show_workspace` | `view` | Switch Packet Tracer's main window between the logical and the physical workspace, for example before a screenshot or a class demo. |
| `simulation_mode` | `on` | Switch between Realtime and Simulation mode. Returns the mode, the simulation clock and how many events are recorded. |
| `simulation_step` | None | Advance the simulation (`forward`, like Capture/Forward), go `back`, or `reset` the event list. Needs Simulation mode. |
| `status` | None | Check whether Packet Tracer is reachable and summarize the open network. When it is not reachable, `problem` explains what to fix. |
| `unlock_activity` | `password` | Give a password-protected activity its password (for its author or instructor) so Packet Tracer reports scores and runs checks. activity_status shows password_confirmed: false when this is needed. |
| `vpn_client` | `device` | Use the VPN app of a PC, laptop or server against an Easy VPN server: `connect` with server, group, group_key, username and password and wait for the tunnel, `disconnect`, or `status`. Returns whether the tunnel is up and the address the server assigned. |
| `watch_events` | `class` | Listen to Packet Tracer's live IPC events for a few seconds and return them: devices and links added or removed, console output, simulation steps, ARP and DHCP activity, and 200 more across 73 classes. Start something (for example with another tool call in parallel, or by hand in Packet Tracer) and see what it triggers. describe_ipc with `events` lists the classes and names. |
| `wireless_status` | `device` | Read the wireless settings of an access point, wireless router or client, and for clients which access point they are associated with. |

## Result checks

- `configure_ios`: verify `completed`, `applied`, `total` and each command result.
- `run_cli` / `run_host_command`: verify `finished` and actual output; a transport-level success is insufficient.
- `status`: `connected` checks the live Cisco session, not just MCP initialization.
- `tp_lire`: continue using `next_offset`; inspect extraction warnings.

## Activity container protection

The gateway refuses the following snapshot-rewriting operations while a `.pka` is active: `add_location`, `rename_location`, `remove_location`, `arrange_devices`, `move_to_location`, `set_background`, `draw`, `remove_drawing`, and `connect_wireless`. Use a separate `.pkt` for these operations or the appropriate visible Cisco controls on a working activity copy.

## Minimal examples

```json
{"tool":"configure_ios","arguments":{"device":"R1","commands":["interface GigabitEthernet0/0","ip address 192.0.2.1 255.255.255.0","no shutdown"],"save":true}}
{"tool":"run_host_command","arguments":{"device":"PC1","command":"ping 192.0.2.20","timeout_secs":20}}
{"tool":"call_ipc","arguments":{"from":"network","steps":[{"method":"getDeviceCount"}]}}
```

For desktop interactions, get a current window ID from `ui_windows`, inspect and capture it, take one action, then inspect again. `ui_click` supports `mouse_button` and `click_count`; `ui_drag` and `ui_scroll` use window-relative coordinates.
