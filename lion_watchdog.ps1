# ============================================================
#  lion_watchdog.ps1
#  Lion desktop-pet watchdog: keeps the pet alive.
#  If the lion process exits WITHOUT a clean-exit marker,
#  relaunch it after 2s. If the user right-clicked "exit"
#  (marker written), stop the loop.
# ============================================================
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$marker = Join-Path $dir 'lion_clean_exit.txt'
$scriptFile = Join-Path $dir 'lion_desktop.ps1'
$pat = 'lion_desktop' + [char]46 + 'ps1'

# already running? (e.g. user double-clicked the bat again) -> exit quietly
$existing = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -like "*$pat*" }
if ($existing) { exit }

Remove-Item $marker -ErrorAction SilentlyContinue

while ($true) {
  $p = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',$scriptFile) -PassThru -WindowStyle Hidden
  $p.WaitForExit()
  if (Test-Path $marker) { Remove-Item $marker -Force -ErrorAction SilentlyContinue; break }
  Start-Sleep -Seconds 2
}
