param(
    [string]$Plan = "data/action_plan.json",
    [string]$Out = "data/engage_results.json",
    [string]$VerifyOut = "data/verify_report.json",
    [double]$MinDelay = 5.0,
    [double]$MaxDelay = 60.0,
    [int]$VerifyConcurrency = 3,
    [switch]$Strict
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Plan)) {
    throw "File plan tidak ditemukan: $Plan"
}

$exe = ".\target\release\x-social-draft-workflow.exe"
if (-not (Test-Path $exe)) {
    Write-Host "Release CLI belum ada, menjalankan cargo build --release..."
    cargo build --release
}

Write-Host "[1/4] Menjalankan eksekusi headless terisolasi + auto-retry + audit paralel (jeda acak $MinDelay-$MaxDelay detik)..."
$engArgs = @(
    "-u", ".agents/skills/x-social-browser-workflow/scripts/engage_posts.py",
    "--plan", $Plan,
    "--out", $Out,
    "--verify-out", $VerifyOut,
    "--min-delay", "$MinDelay",
    "--max-delay", "$MaxDelay",
    "--verify-concurrency", "$VerifyConcurrency"
)
if ($Strict) { $engArgs += "--strict" }
python @engArgs

Write-Host "[2/4] Menyinkronkan konfirmasi Like & Reply terverifikasi ke SQLite..."
$results = Get-Content -Path $Out -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($row in $results) {
    if ($row.liked -eq $true -and $row.replied -eq $true) {
        if ($row.reply_note -ne "already_replied") {
            try {
                & $exe confirm-posted --draft-id $row.draft_id | Out-Null
            } catch {
                Write-Host "Info: draft $($row.draft_id) sudah tercatat atau dilewati."
            }
        }
        if ($row.like_note -eq "liked_now" -or $row.like_note -eq "already_liked") {
            try {
                & $exe confirm-liked --post-id $row.post_id | Out-Null
            } catch {
                Write-Host "Info: like post $($row.post_id) sudah tercatat atau dilewati."
            }
        }
    }
}

Write-Host "[3/4] Strict SQLite Completeness Audit (Tabel):"
$auditArgs = @("audit", "--plan", $Plan)
if ($Strict) { $auditArgs += "--strict" }
& $exe @auditArgs

Write-Host "[4/4] Laporan hasil akhir (Tabel):"
& $exe report
