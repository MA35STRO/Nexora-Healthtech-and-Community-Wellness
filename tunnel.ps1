# Share Kawan on phones / other devices with a temporary public HTTPS link (Cloudflare quick tunnel).
# Phones need HTTPS for camera access, which this provides. No Cloudflare account needed.
#
#   .\tunnel.ps1            start app (if needed) + tunnel, print the link, Ctrl+C to stop
#
# The link changes every run and works only while this window is open.
# There is NO login: anyone with the link can use the app — share it only with people you trust.
param([switch]$NoWait)   # -NoWait: print the link and leave everything running (used for testing)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$tools = Join-Path $root 'tools'
$cf = Join-Path $tools 'cloudflared.exe'
$started = @()

function Test-Health($base) {
  try { return (Invoke-RestMethod "$base/api/health" -TimeoutSec 5).ok -eq $true } catch { return $false }
}

# 1. cloudflared (downloaded once from Cloudflare's official GitHub releases, signature checked)
if (-not (Test-Path $cf)) {
  Write-Host 'Downloading cloudflared (one time, ~55 MB)...'
  New-Item -ItemType Directory -Force $tools | Out-Null
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  Invoke-WebRequest 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile $cf -UseBasicParsing
}
$sig = Get-AuthenticodeSignature $cf
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notlike '*Cloudflare, Inc.*') {
  Remove-Item $cf -Force
  throw 'cloudflared.exe is not validly signed by Cloudflare - deleted it. Please try again.'
}

# 2. the app itself (reuse it if it is already running)
if (-not (Test-Health 'http://127.0.0.1:8000')) {
  if (-not (Test-Path (Join-Path $root 'frontend\dist\index.html'))) {
    Write-Host 'Building the dashboard...'
    Push-Location (Join-Path $root 'frontend')
    if (-not (Test-Path node_modules)) { npm install }
    npm run build
    Pop-Location
  }
  $py = Join-Path $root 'backend\.venv\Scripts\python.exe'
  if (-not (Test-Path $py)) { throw 'Python environment missing - run .\start.ps1 once first.' }
  Write-Host 'Starting the Kawan hub...'
  $server = Start-Process $py -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000' `
    -WorkingDirectory (Join-Path $root 'backend') -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $root 'server.log') -RedirectStandardError (Join-Path $root 'server.err.log')
  $started += $server
  for ($i = 0; $i -lt 30 -and -not (Test-Health 'http://127.0.0.1:8000'); $i++) { Start-Sleep 1 }
  if (-not (Test-Health 'http://127.0.0.1:8000')) { throw 'The hub did not start - see server.err.log' }
}

try {
  # 3. the tunnel
  Write-Host 'Opening the secure tunnel...'
  $log = Join-Path $tools 'tunnel.log'
  if (Test-Path $log) { Remove-Item $log -Force }
  $tunnel = Start-Process $cf -ArgumentList 'tunnel', '--no-autoupdate', '--url', 'http://127.0.0.1:8000' `
    -WindowStyle Hidden -PassThru -RedirectStandardError $log -RedirectStandardOutput (Join-Path $tools 'tunnel.out.log')
  $started += $tunnel

  $url = $null
  for ($i = 0; $i -lt 40 -and -not $url; $i++) {
    Start-Sleep 1
    if (Test-Path $log) {
      $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1
      if ($m) { $url = $m.Matches[0].Value }
    }
  }
  if (-not $url) { throw "No tunnel link received - check your internet connection ($log)" }

  # a new link takes a few seconds before it answers
  for ($i = 0; $i -lt 30 -and -not (Test-Health $url); $i++) { Start-Sleep 2 }
  if (-not (Test-Health $url)) { throw "The tunnel link is not answering yet: $url (try running again)" }

  try { Set-Clipboard $url } catch {}
  Write-Host ''
  Write-Host '  Kawan is live for phones and other devices:' -ForegroundColor Green
  Write-Host ''
  Write-Host "    Patient (companion):  $url" -ForegroundColor Cyan
  Write-Host "    Caregiver dashboard:  $url/caregiver" -ForegroundColor Cyan
  Write-Host ''
  Write-Host '  (link copied to clipboard) Open it in Chrome/Safari and allow the camera.'
  Write-Host '  No login - share only with people you trust. The link changes every run.' -ForegroundColor Yellow
  Write-Host ''

  if ($NoWait) { $started = @(); return }
  Write-Host 'Press Ctrl+C to stop sharing.'
  while (-not $tunnel.HasExited) { Start-Sleep 1 }
  Write-Host 'The tunnel stopped.' -ForegroundColor Yellow
}
finally {
  foreach ($p in $started) { if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force } }
  if ($started.Count) { Write-Host 'Stopped the tunnel and anything this script started.' }
}
