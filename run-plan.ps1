param(
    [string]$Plan = "data/action_plan.json",
    [string]$Out = "data/engage_results.json",
    [double]$MinDelay = 5.0,
    [double]$MaxDelay = 60.0
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

Write-Host "[1/3] Menjalankan eksekusi headless terisolasi (jeda acak $MinDelay-$MaxDelay detik)..."
python -u .agents/skills/x-social-browser-workflow/scripts/engage_posts.py `
    --plan $Plan `
    --out $Out `
    --min-delay $MinDelay `
    --max-delay $MaxDelay

Write-Host "[2/3] Mencatat konfirmasi Like & Reply terverifikasi ke SQLite..."
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
            & $exe confirm-liked --post-id $row.post_id | Out-Null
        }
    }
}

Write-Host "[3/3] Laporan hasil akhir:"
& $exe report
