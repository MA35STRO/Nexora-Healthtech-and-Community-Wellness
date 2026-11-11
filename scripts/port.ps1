# Picks the port Kawan runs on (dot-sourced by start.ps1 and tunnel.ps1).
#
# 8000 is the default, but other software often takes it (Oracle Database's web listener uses
# 8000 and 8001, for example). Then we fall back to the next free port instead of failing.
# Set KAWAN_PORT to force one port. The chosen port is saved in .kawan-port so tunnel.ps1 can
# find an app that start.ps1 already started.

$KawanPortFile = Join-Path (Split-Path $PSScriptRoot -Parent) '.kawan-port'

function Test-PortFree([int]$Port) {
  try {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
    $listener.Start()
    $listener.Stop()
    return $true
  } catch { return $false }
}

function Get-PortOwner([int]$Port) {
  try {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop | Select-Object -First 1
    return (Get-Process -Id $conn.OwningProcess -ErrorAction Stop).ProcessName + '.exe'
  } catch { return 'another program' }
}

function Get-KawanPort {
  if ($env:KAWAN_PORT) {
    $p = [int]$env:KAWAN_PORT
    if (-not (Test-PortFree $p)) { throw "KAWAN_PORT=$p is already used by $(Get-PortOwner $p)." }
    return $p
  }
  foreach ($p in 8000, 8080, 8765, 8888, 18000) {
    if (Test-PortFree $p) {
      if ($p -ne 8000) {
        Write-Host "Port 8000 is used by $(Get-PortOwner 8000), so Kawan will use port $p instead." -ForegroundColor Yellow
      }
      return $p
    }
  }
  # all the usual ones are busy: let Windows pick any free port
  $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
  $listener.Start()
  $p = $listener.LocalEndpoint.Port
  $listener.Stop()
  Write-Host "The usual ports are busy, so Kawan will use port $p." -ForegroundColor Yellow
  return $p
}

function Get-SavedKawanPort {
  if (Test-Path $KawanPortFile) { return [int](Get-Content $KawanPortFile -Raw).Trim() }
  return $null
}

function Save-KawanPort([int]$Port) { Set-Content -Path $KawanPortFile -Value $Port -Encoding ascii }
