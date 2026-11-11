# Validation

## Offline suite

Install `requirements-dev.txt` in an isolated environment and run `python -m pytest`. Default tests do not require Cisco and do not click or type in desktop windows. They exercise file boundaries, copies and hashes, document extraction, VLSM, backups, result forwarding, Windows targeting and input validation, and installer safeguards. The symlink case can be skipped when Windows does not allow symlink creation.

## Opt-in live checks

These scripts require a running registered Cisco instance and the installed connector's Python interpreter:

```powershell
$python = "$env:USERPROFILE\.vibe\extensions\packettracer-mcp\.venv\Scripts\python.exe"
& $python .\tests\smoke_installed.py
```

The smoke check verifies tool discovery, IPC connection, Cisco window inspection and rejection of an invalid window identifier. It writes an ignored local validation report. Registration regeneration is optional.

The full test **creates and changes a demonstration network**, after backing up the currently open network. It creates a router, switch and two PCs; cables and configures them; checks IOS and ping; follows ICMP simulation; saves/reopens; and verifies connectivity again. Optional activity/document arguments check a working `.pka` copy and an assignment.

```powershell
& $python .\tests\e2e_live.py `
  --home "$env:USERPROFILE\.vibe\extensions\packettracer-mcp" `
  --output "$env:TEMP\packettracer-validation.json"

& $python .\tests\e2e_live.py `
  --home "$env:USERPROFILE\.vibe\extensions\packettracer-mcp" `
  --output "$env:TEMP\packettracer-validation.json" `
  --activity 'C:\Downloads\example-lab.pka' `
  --assignment 'C:\Downloads\example-assignment.pdf'
```

Local Windows checks with Packet Tracer 9.0.1 covered creation/cabling, IOS configuration, PC-to-PC ping, ICMP simulation decisions, save/reopen, physical/logical switching, logical capture, and activity-copy reading/saving while the original SHA-256 remained unchanged. This validates representative workflows, not every Cisco feature or desktop control.
