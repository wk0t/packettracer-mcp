[CmdletBinding()]
param(
    [string]$Archive,
    [switch]$SkipVibe,
    [string]$PacketTracerHome
)

$ErrorActionPreference = 'Stop'
$installer = Join-Path $PSScriptRoot 'install.py'
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
$uvPath = if ($uvCommand) { $uvCommand.Source } else { Join-Path $env:USERPROFILE '.local\bin\uv.exe' }
if (-not (Test-Path -LiteralPath $uvPath -PathType Leaf)) {
    throw 'uv is required. Install uv from https://docs.astral.sh/uv/getting-started/installation/ and rerun this script.'
}

$installerArgs = @()
if ($Archive) { $installerArgs += @('--archive', $Archive) }
if ($SkipVibe) { $installerArgs += '--skip-vibe' }
if ($PacketTracerHome) { $installerArgs += @('--packet-tracer-home', $PacketTracerHome) }
& $uvPath run --no-project --python 3.12 python $installer @installerArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
