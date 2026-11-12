# Validation

## Check an installed connector

Run the installed `doctor.py` with the installation's Python interpreter. The following PowerShell commands select the default installation; replace `$connectorHome` for a custom directory.

```powershell
$localData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $env:USERPROFILE 'AppData\Local' }
$connectorHome = Join-Path $localData 'PacketTracerMCP'
$python = Join-Path $connectorHome '.venv\Scripts\python.exe'
$doctor = Join-Path $connectorHome 'doctor.py'
$settings = Join-Path $connectorHome 'settings.json'
& $python $doctor --settings $settings
```

The check inspects installed files, dependencies, settings and the engine, then performs real MCP initialization, discovers the tools and checks Cisco's connection. It does not modify lab networks or send desktop input. Expect **87 tools** and `connected: true` when Cisco is open and registered.

| Exit code | Meaning | Next step |
| --- | --- | --- |
| `0` | Installation and MCP connection are ready; Cisco is connected. | Connect the client and begin a small read-only task. |
| `2` | The connector is ready, but Cisco is unavailable or not registered. | Open Cisco and check [registration and listening](installation.md#register-in-cisco), then run the check again. |
| `1` | An installation, dependency, settings or MCP startup check failed. | Follow the reported error; rerun the installer if files or dependencies are missing. |

For a check without contacting the simulator:

```powershell
& $python $doctor --settings $settings --offline
```

In offline mode, exit `0` means the installation checks passed; it does not confirm a live Cisco connection. Add `--json` to either command for machine-readable check results and recovery actions.

## Offline developer suite

From the repository checkout:

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

Default tests require no running Cisco instance and do not click or type in desktop windows. They cover file boundaries, working copies and hashes, document extraction, VLSM, backups, result forwarding, Windows targeting, input validation and installer safeguards. The symlink case can be skipped when Windows does not allow symlink creation.

Protocol tests negotiate MCP initialization, discover the same 87 tools from independently named clients, and check structured results, image content and errors. Runtime checks cover explicit settings, environment configuration and launches from outside the installation directory. Installer checks verify that existing client configurations stay unchanged.

## Opt-in live checks

Run these scripts from the repository checkout with a running, registered Cisco instance and the installed interpreter selected above.

```powershell
& $python .\tests\smoke_installed.py --home $connectorHome
```

The smoke check verifies 87 tools, the IPC connection, Cisco window inspection and rejection of an invalid window identifier. It does not change lab networks, send valid desktop input or regenerate registration. It writes the ignored `validation-installation.json` report in the checkout.

The full test **creates and changes a demonstration network**, after backing up the currently open network. It creates a router, switch and two PCs; cables and configures them; checks IOS and ping; follows ICMP simulation; saves and reopens the network; and verifies connectivity again.

```powershell
& $python .\tests\e2e_live.py `
  --home $connectorHome `
  --output "$env:TEMP\packettracer-validation.json"
```

Optional `--activity` and `--assignment` arguments check a working `.pka` copy and its assignment:

```powershell
& $python .\tests\e2e_live.py `
  --home $connectorHome `
  --output "$env:TEMP\packettracer-validation.json" `
  --activity 'C:\Users\YOUR_USERNAME\Downloads\example-lab.pka' `
  --assignment 'C:\Users\YOUR_USERNAME\Downloads\example-assignment.pdf'
```

## Validated scope

Local Windows checks with Packet Tracer 9.0.1 covered creation and cabling, IOS configuration, PC-to-PC ping, ICMP simulation decisions, save/reopen, physical/logical switching, logical capture, and activity-copy reading/saving while the original SHA-256 remained unchanged.

These checks cover representative workflows and the standard MCP stdio transport. Windows x64 with Packet Tracer 9.0.1 remains the validated runtime. Other Cisco releases and individual client integrations require separate validation.
