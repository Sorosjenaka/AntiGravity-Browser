param(
    [string]$Browser = "auto",
    [string]$Profile = "",
    [string]$ExePath = "",
    [string]$Handle = "",
    [string]$DisplayName = "",
    [int]$Port = 0,
    [switch]$NoShortcut,
    [switch]$NoDetect
)

$ErrorActionPreference = "Stop"

Write-Host "[1/5] Checking Rust & building release binary..."
cargo test
cargo build --release

Write-Host "[2/5] Checking Python WebSocket dependency..."
python -c "import websockets" 2>$null
if ($LASTEXITCODE -ne 0) {
    python -m pip install websockets
}

Write-Host "[3/5] Initializing local SQLite database..."
$exe = ".\target\release\x-social-draft-workflow.exe"
& $exe init

Write-Host "[4/5] Connecting browser ($Browser), creating isolated profile & shortcut, and auto-detecting X user..."
$connArgs = @("connect-browser", "--browser", $Browser)
if ($Profile -ne "") { $connArgs += @("--profile", $Profile) }
if ($ExePath -ne "") { $connArgs += @("--exe-path", $ExePath) }
if ($Port -gt 0) { $connArgs += @("--port", "$Port") }
if ($NoShortcut) { $connArgs += "--no-shortcut" }
if ($NoDetect -or ($Handle -ne "" -and $DisplayName -ne "")) { $connArgs += "--no-detect" }
& $exe @connArgs

if ($Handle -ne "" -and $DisplayName -ne "") {
    & $exe confirm-account --handle $Handle --display-name $DisplayName
}

Write-Host "[5/5] Current status:"
& $exe status
