param(
    [string]$Browser = "",
    [string]$Profile = "",
    [string]$ExePath = "",
    [string]$Handle = "",
    [string]$DisplayName = "",
    [int]$Port = 0,
    [ValidateSet("ask", "default", "custom")]
    [string]$PromptMode = "ask",
    [string]$PromptFile = "",
    [switch]$NoShortcut,
    [switch]$NoDetect,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

Write-Host "[1/6] Checking Rust & building release binary..."
cargo test
cargo build --release

Write-Host "[2/6] Checking Python WebSocket dependency..."
python -c "import websockets" 2>$null
if ($LASTEXITCODE -ne 0) {
    python -m pip install websockets
}

Write-Host "[3/6] Initializing local SQLite database..."
$exe = ".\target\release\x-social-draft-workflow.exe"
& $exe init

$effectiveBrowser = $Browser.Trim()
if ($effectiveBrowser -eq "") {
    if ($NonInteractive) {
        $effectiveBrowser = "auto"
    } else {
        $effectiveBrowser = "ask"
    }
}

Write-Host "[4/6] Selecting & connecting browser ($effectiveBrowser), creating isolated profile & shortcut, and auto-detecting X user..."
$connArgs = @("connect-browser", "--browser", $effectiveBrowser)
if ($Profile -ne "") { $connArgs += @("--profile", $Profile) }
if ($ExePath -ne "") { $connArgs += @("--exe-path", $ExePath) }
if ($Port -gt 0) { $connArgs += @("--port", "$Port") }
if ($NoShortcut) { $connArgs += "--no-shortcut" }
if ($NoDetect -or ($Handle -ne "" -and $DisplayName -ne "")) { $connArgs += "--no-detect" }
& $exe @connArgs

if ($Handle -ne "" -and $DisplayName -ne "") {
    & $exe confirm-account --handle $Handle --display-name $DisplayName
}

Write-Host "[5/6] Configuring reply prompt & previewing sample outputs..."
$promptArgs = @(".agents/skills/x-social-browser-workflow/scripts/prompt_setup.py", "--cli-path", $exe, "--mode", $PromptMode)
if ($PromptFile -ne "") { $promptArgs += @("--prompt-file", $PromptFile) }
if ($NonInteractive) { $promptArgs += "--non-interactive" }
python @promptArgs

Write-Host "[6/6] Current status:"
& $exe status
