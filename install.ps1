[CmdletBinding()]
param(
    [string]$Archive,
    [string]$InstallDir,
    [string]$PacketTracerHome,
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
$osArchitecture = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
if ($env:OS -ne 'Windows_NT' -or $osArchitecture -notin @('AMD64', 'x86_64')) {
    throw 'This installer requires Windows x64. Use a Windows x64 computer and rerun this script.'
}
$installer = Join-Path $PSScriptRoot 'install.py'
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
$uvPath = if ($uvCommand) { $uvCommand.Source } else { Join-Path $env:USERPROFILE '.local\bin\uv.exe' }
if (-not (Test-Path -LiteralPath $uvPath -PathType Leaf)) {
    throw 'uv is required. Install uv from https://docs.astral.sh/uv/getting-started/installation/ and rerun this script.'
}

# Discover existing interpreters without invoking uv run, creating a cache, or
# downloading Python. This also keeps -Check read-only on a fresh checkout.
$pythonCandidates = [System.Collections.Generic.List[string]]::new()
$managedRoots = @($env:UV_PYTHON_INSTALL_DIR)
if ($env:APPDATA) { $managedRoots += Join-Path $env:APPDATA 'uv\python' }
foreach ($root in $managedRoots) {
    if ($root -and (Test-Path -LiteralPath $root -PathType Container)) {
        foreach ($folder in (Get-ChildItem -LiteralPath $root -Directory | Where-Object Name -Like 'cpython-*' | Sort-Object Name)) {
            $pythonCandidates.Add((Join-Path $folder.FullName 'python.exe'))
        }
    }
}
foreach ($name in @('python3.12', 'python', 'python3')) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if ($command) { $pythonCandidates.Add($command.Source) }
}
$probe = 'import struct, sys; sys.exit(1) if sys.version_info < (3, 12) or struct.calcsize(''P'') != 8 else print(sys.executable)'
$pythonPath = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        try {
            $found = & $candidate -I -B -c $probe 2>$null
            if ($LASTEXITCODE -eq 0 -and $found) { $pythonPath = [string]$found; break }
        } catch { continue }
    }
}
if (-not $pythonPath) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            $found = & $launcher.Source -3 -I -B -c $probe 2>$null
            if ($LASTEXITCODE -eq 0 -and $found) { $pythonPath = [string]$found }
        } catch { $pythonPath = $null }
    }
}
if (-not $pythonPath) {
    if ($Check) {
        throw 'Python 3.12 or newer was not found. Run uv python install 3.12, then rerun this script with -Check. The check did not install or download anything.'
    }
    [Console]::Error.WriteLine('[setup] Preparing Python 3.12 with uv...')
    & $uvPath python install --no-bin --no-registry '3.12' | ForEach-Object { [Console]::Error.WriteLine($_) }
    if ($LASTEXITCODE -ne 0) {
        throw 'Python setup failed. Check your network or run uv python install 3.12, then rerun this script.'
    }
    $found = & $uvPath python find --no-project --no-python-downloads '3.12'
    if ($LASTEXITCODE -ne 0 -or -not $found -or -not (Test-Path -LiteralPath ([string]$found) -PathType Leaf)) {
        throw 'The prepared Python interpreter was not found. Run uv python find 3.12 and verify its executable path, then retry.'
    }
    $pythonPath = [string]$found
}

$installerArgs = @()
if ($Archive) { $installerArgs += @('--archive', $Archive) }
if ($InstallDir) { $installerArgs += @('--install-dir', $InstallDir) }
if ($PacketTracerHome) { $installerArgs += @('--packet-tracer-home', $PacketTracerHome) }
if ($Check) { $installerArgs += '--check' }
& $pythonPath -B $installer @installerArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
