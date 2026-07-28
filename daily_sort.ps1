<#
  daily_sort.ps1 — unattended daily maintenance for one or more source playlists.

  This is a TEMPLATE. Set $SOURCES below to YOUR own source playlist IDs
  (the playlists you want drained/sorted) — get them from:
      .\venv\Scripts\python.exe youtube_cleaner.py playlists
  Then wire this script into a Windows Scheduled Task to run daily.

  Behavior:
    * Clears dead (deleted/private) videos across all playlists first, freeing slots.
    * OPT-IN age-purge: if config.json has a `purge` block (enabled + playlists),
      deletes videos older than N years from those playlists to make room. Safe
      no-op when no purge config is present, so existing setups are unaffected.
    * Sorts each playlist in $SOURCES (in order) into topic playlists using your
      config.json / rules.json classifier. Unmatched videos are left in place.
    * Each run is capped by -MaxMoves (default 90 per source ~= 9,000 quota units)
      to stay under the 10,000 units/day API cap. If quota runs out mid-run the
      tool stops gracefully and resumes next day (already-sorted videos skip).
    * Insert-before-delete: a crash can never lose a video.

  Idempotent: once a source playlist has nothing left to sort it moves nothing.

  NOTE (OAuth): while the Google app is in "Testing" mode the refresh token
  expires ~7 days after the last interactive login. If a run logs an auth error,
  run  .\venv\Scripts\python.exe youtube_cleaner.py auth  once to re-login.
#>
param(
  [int]$MaxMoves = 90,
  [int]$MaxDeletes = 40
)

$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $here

$py  = Join-Path $here "venv\Scripts\python.exe"
$log = Join-Path $here "output\daily-sort.log"
$env:YTQ_NO_BROWSER = "1"   # never pop a browser under the scheduler

# ---- EDIT ME: your source playlist IDs, sorted in the order you want drained ----
# Example: $SOURCES = @("PLxxxxxxxxxxxxxxxxxx", "FLxxxxxxxxxxxxxxxxxx")
$SOURCES = @(
  # "PLxxxxxxxxxxxxxxxxxx",
)

if (-not (Test-Path (Split-Path $log))) { New-Item -ItemType Directory (Split-Path $log) | Out-Null }
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content $log "`n========== daily_sort @ $stamp (cap $MaxMoves/source) =========="

if ($SOURCES.Count -eq 0) {
  Add-Content $log "No $SOURCES configured — edit daily_sort.ps1 and set your playlist IDs. Nothing to do."
  Write-Warning "Edit daily_sort.ps1: set `$SOURCES to your source playlist IDs."
  return
}

# 0) Clear dead (deleted/private/unavailable) videos across all playlists first.
#    Frees playlist slots BEFORE the sort inserts. ~50 units each; one-time
#    backlog then near-zero on later runs. --max-deletes caps quota per run.
#    Add titles to --protect (comma-separated) if you want to skip some playlists.
& $py -u youtube_cleaner.py remove-unavailable --execute --yes --max-deletes $MaxDeletes 2>&1 |
  Tee-Object -FilePath $log -Append

# 0b) Scheduled age-purge (OPT-IN). Deletes videos older than N years from the
#     playlists YOU list in config.json's `purge` block, to keep them under the
#     5,000-item cap and make room for new saves. This is a SAFE NO-OP until you
#     add  "purge": { "enabled": true, "years": 2, "playlists": [...] }  to
#     config.json -- with no purge config it deletes nothing and exits instantly.
& $py -u youtube_cleaner.py autopurge --execute --yes --daily-budget $MaxDeletes 2>&1 |
  Tee-Object -FilePath $log -Append

# 1) Sort each configured source playlist, in order. Unmatched videos stay put.
foreach ($src in $SOURCES) {
  & $py -u youtube_cleaner.py sort --source $src --execute --yes --max-moves $MaxMoves 2>&1 |
    Tee-Object -FilePath $log -Append
}

Add-Content $log "---------- daily_sort finished @ $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ----------"
