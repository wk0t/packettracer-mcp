# Validation

## Offline suite

Install `requirements-dev.txt` in an isolated environment and run `python -m pytest`. Default tests do not require Cisco and do not click or type in desktop windows. They exercise file boundaries, copies and hashes, document extraction, VLSM, backups, result forwarding, Windows targeting and input validation, and installer safeguards. The symlink case can be skipped when Windows does not allow symlink creation.

Protocol tests negotiate standard MCP initialization, discover the same 87 tools from independently named clients, and check structured results, image content and errors. Runtime tests cover explicit settings, environment configuration and launching from a working directory outside the installation. Installer tests verify that existing client configurations remain unchanged.

## Opt-in live checks

These scripts act as standalone local stdio MCP clients. They require a running registered Cisco instance and the installed connector's Python interpreter. Run them from the repository checkout. The following PowerShell setup uses the default installation; assign your chosen directory to `$connectorHome` if you used `-InstallDir`.

```powershell
$localData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $env:USERPROFILE 'AppData\Local' }
$connectorHome = Join-Path $localData 'PacketTracerMCP'
$python = Join-Path $connectorHome '.venv\Scripts\python.exe'
& $python .\tests\smoke_installed.py

# For a custom installation directory:
& $python .\tests\smoke_installed.py --home $connectorHome
```

The smoke check defaults to `%LOCALAPPDATA%\PacketTracerMCP` (or `%USERPROFILE%\AppData\Local\PacketTracerMCP`), with `--home` available for custom installations. It passes the selected installation's settings path explicitly. It verifies the 87 tools, IPC connection, Cisco window inspection and rejection of an invalid window identifier. It does not configure or change lab networks, send valid desktop input, or regenerate registration. It writes an ignored local validation report.

The full test **creates and changes a demonstration network**, after backing up the currently open network. It creates a router, switch and two PCs; cables and configures them; checks IOS and ping; follows ICMP simulation; saves/reopens; and verifies connectivity again. Optional activity/document arguments check a working `.pka` copy and an assignment.

```powershell
& $python .\tests\e2e_live.py `
  --home $connectorHome `
  --output "$env:TEMP\packettracer-validation.json"

& $python .\tests\e2e_live.py `
  --home $connectorHome `
  --output "$env:TEMP\packettracer-validation.json" `
  --activity 'C:\Downloads\example-lab.pka' `
  --assignment 'C:\Downloads\example-assignment.pdf'
```

Local Windows checks with Packet Tracer 9.0.1 covered creation/cabling, IOS configuration, PC-to-PC ping, ICMP simulation decisions, save/reopen, physical/logical switching, logical capture, and activity-copy reading/saving while the original SHA-256 remained unchanged. These checks validate representative simulator workflows, not every Cisco feature or desktop control. Local stdio compatibility follows the MCP transport contract; this is not a claim that every MCP client has been tested. Windows x64 with Packet Tracer 9.0.1 remains the validated simulator runtime.
