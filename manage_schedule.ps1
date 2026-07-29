<#
  manage_schedule.ps1 -- inspect and control the unattended daily maintenance.

  This tool does two independent things so you can turn off exactly what you want:

    OPTION 1 (age-purge only) -- flip `purge.enabled` in config.json off/on.
      Stops the permanent age-based DELETES (`autopurge`) while leaving the daily
      sort + dead-video cleanup running.

    OPTION 2 (the whole schedule) -- pause / resume / remove the Windows Scheduled
      Task that runs daily_sort.ps1. Stops EVERYTHING the daily job does
      (remove-unavailable + autopurge + sort).

  NOTE: This app does NOT create schedules on its own. The "YouTube Daily Sort"
  task (if present) was set up manually. This script just manages it for you.

  Usage:
    powershell -ExecutionPolicy Bypass -File .\manage_schedule.ps1 status
    powershell -ExecutionPolicy Bypass -File .\manage_schedule.ps1 install-task -Time 12:30
    powershell -ExecutionPolicy Bypass -File .\manage_schedule.ps1 disable-purge
    powershell -ExecutionPolicy Bypass -File .\manage_schedule.ps1 enable-purge
    powershell -ExecutionPolicy Bypass -File .\manage_schedule.ps1 pause-task
    powershell -ExecutionPolicy Bypass -File .\manage_schedule.ps1 resume-task
    powershell -ExecutionPolicy Bypass -File .\manage_schedule.ps1 remove-task    # add -Force to skip the prompt

  Belt-and-suspenders "stop purge completely":
    .\manage_schedule.ps1 disable-purge   # config can never delete
    .\manage_schedule.ps1 pause-task      # the daily job can't fire at all
#>
param(
  [ValidateSet('status','install-task','disable-purge','enable-purge','pause-task','resume-task','remove-task')]
  [string]$Action = 'status',
  [string]$TaskName = 'YouTube Daily Sort',
  [string]$Time = '12:30',
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
$here    = Split-Path -Parent $MyInvocation.MyCommand.Definition
$cfgPath = Join-Path $here 'config.json'

function Get-Task {
  Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
}

function Get-PurgeEnabled {
  # Returns $true / $false / $null (null = no purge config at all = already OFF)
  if (-not (Test-Path $cfgPath)) { return $null }
  try { $j = Get-Content $cfgPath -Raw | ConvertFrom-Json } catch { return $null }
  if (-not $j.PSObject.Properties['purge']) { return $null }
  return [bool]$j.purge.enabled
}

function Show-Status {
  Write-Host ''
  Write-Host '=== Daily maintenance status ===' -ForegroundColor Cyan

  $t = Get-Task
  if ($t) {
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host ("Scheduled task : '{0}'  [{1}]" -f $TaskName, $t.State)
    Write-Host ("  Last run     : {0}  (result {1})" -f $info.LastRunTime, $info.LastTaskResult)
    Write-Host ("  Next run     : {0}" -f $info.NextRunTime)
    Write-Host "  Runs         : daily_sort.ps1 -> remove-unavailable + autopurge + sort"
  } else {
    Write-Host ("Scheduled task : NOT FOUND ('{0}')" -f $TaskName) -ForegroundColor Yellow
    Write-Host "  Nothing is scheduled -- the daily job will not run."
  }

  $p = Get-PurgeEnabled
  Write-Host ''
  if     ($null -eq $p) { Write-Host "Age-purge      : OFF  (no purge config in config.json -- autopurge deletes nothing)" -ForegroundColor Green }
  elseif ($p)           { Write-Host "Age-purge      : ON   (purge.enabled = true -- autopurge WILL delete old videos on each run)" -ForegroundColor Red }
  else                  { Write-Host "Age-purge      : OFF  (purge.enabled = false)" -ForegroundColor Green }
  Write-Host ''
}

function Set-PurgeEnabled([bool]$val) {
  if (-not (Test-Path $cfgPath)) {
    if (-not $val) {
      Write-Host "No config.json found -- age-purge is already OFF (autopurge no-ops without a purge config). Nothing to change." -ForegroundColor Green
    } else {
      Write-Warning "No config.json found. Create one with a purge block (enabled/years/playlists) first -- see README. Not enabling."
    }
    return
  }
  $j = Get-Content $cfgPath -Raw | ConvertFrom-Json
  if (-not $j.PSObject.Properties['purge']) {
    if (-not $val) {
      Write-Host "config.json has no purge block -- age-purge is already OFF. Nothing to change." -ForegroundColor Green
      return
    }
    $j | Add-Member -NotePropertyName purge -NotePropertyValue ([pscustomobject]@{ enabled = $false })
  }
  $j.purge.enabled = $val
  ($j | ConvertTo-Json -Depth 20) | Set-Content $cfgPath -Encoding UTF8
  if ($val) {
    Write-Host "purge.enabled = true written to config.json. autopurge will delete old videos on the next run." -ForegroundColor Yellow
    Write-Host "Make sure purge.playlists / purge.years are set the way you want (see README)."
  } else {
    Write-Host "purge.enabled = false written to config.json. autopurge will delete nothing from now on." -ForegroundColor Green
    Write-Host "(The daily task still runs sort + dead-video cleanup. Use 'pause-task' to stop the whole job.)"
  }
}

function Require-Task {
  $t = Get-Task
  if (-not $t) {
    Write-Warning ("No scheduled task named '{0}' -- nothing to do. (Run 'status' to confirm.)" -f $TaskName)
    return $null
  }
  return $t
}

switch ($Action) {

  'status'        { Show-Status }

  'install-task' {
    $scriptPath = Join-Path $here 'daily_sort.ps1'
    if (-not (Test-Path $scriptPath)) {
      Write-Warning "daily_sort.ps1 not found next to this script ($scriptPath). Cannot create the task."
      break
    }
    try { $at = [datetime]::Parse($Time) }
    catch { Write-Warning "Could not parse -Time '$Time'. Use 24h HH:mm, e.g. -Time 12:30 or -Time 02:00."; break }

    $existing = Get-Task
    if ($existing -and -not $Force) {
      $ans = Read-Host ("A task named '{0}' already exists. Replace it? Type YES to overwrite" -f $TaskName)
      if ($ans -ne 'YES') { Write-Host 'Aborted - existing task left in place.'; break }
    }

    # Warn (don't block) if the template still has no source playlists set.
    $srcSet = Select-String -Path $scriptPath -Pattern '^\s*"[A-Za-z0-9_-]{10,}"\s*,' -Quiet
    if (-not $srcSet) {
      Write-Warning "daily_sort.ps1 has no `$SOURCES set yet - the sort step will do nothing until you edit it."
    }

    $me       = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $taskAction = New-ScheduledTaskAction -Execute 'powershell.exe' `
                  -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $scriptPath) `
                  -WorkingDirectory $here
    $trigger  = New-ScheduledTaskTrigger -Daily -At $at
    $principal= New-ScheduledTaskPrincipal -UserId $me -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    $desc     = "Daily YouTube maintenance (remove-unavailable + opt-in age-purge + sort) via daily_sort.ps1. User-created; delete with: manage_schedule.ps1 remove-task"

    Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $trigger `
      -Principal $principal -Settings $settings -Description $desc -Force | Out-Null

    Write-Host ("Created scheduled task '{0}' - runs daily at {1} (only while you're logged in)." -f $TaskName, $at.ToString('HH:mm')) -ForegroundColor Green
    Write-Host "It runs: remove-unavailable + autopurge (no-op until you enable purge) + sort."
    Write-Host "Reminder: when you're done, delete it with  .\manage_schedule.ps1 remove-task" -ForegroundColor Yellow
    Write-Host "First, make sure you've run 'python youtube_cleaner.py auth' and set `$SOURCES in daily_sort.ps1."
  }

  'disable-purge' { Set-PurgeEnabled $false }

  'enable-purge'  { Set-PurgeEnabled $true }

  'pause-task' {
    if (Require-Task) {
      Disable-ScheduledTask -TaskName $TaskName | Out-Null
      Write-Host ("Paused '{0}'. It will NOT run until you 'resume-task'. (Reversible -- nothing deleted.)" -f $TaskName) -ForegroundColor Green
    }
  }

  'resume-task' {
    if (Require-Task) {
      Enable-ScheduledTask -TaskName $TaskName | Out-Null
      Write-Host ("Resumed '{0}'. The daily job is active again." -f $TaskName) -ForegroundColor Yellow
    }
  }

  'remove-task' {
    if (Require-Task) {
      if (-not $Force) {
        $ans = Read-Host ("Permanently DELETE the scheduled task '{0}'? This cannot be undone (you'd re-create it manually). Type YES to confirm" -f $TaskName)
        if ($ans -ne 'YES') { Write-Host 'Aborted -- task left in place.'; break }
      }
      Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
      Write-Host ("Deleted scheduled task '{0}'. The daily job is fully removed." -f $TaskName) -ForegroundColor Green
      Write-Host "(Your files, config, and OAuth token are untouched. Already-deleted videos stay deleted.)"
    }
  }
}
