# One-command start (Windows): installs what's missing, builds the dashboard, runs everything on
# http://localhost:8000 (or the next free port if 8000 is taken - the address is printed below).
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
. .\scripts\port.ps1
if (-not (Test-Path backend\.venv)) {
  Write-Host 'Creating Python environment...'
  if (Get-Command uv -ErrorAction SilentlyContinue) { uv venv --python 3.12 backend\.venv; uv pip install --python backend\.venv\Scripts\python.exe -r backend\requirements.txt }
  else { py -3.12 -m venv backend\.venv; backend\.venv\Scripts\python -m pip install -r backend\requirements.txt }
}
Push-Location frontend
if (-not (Test-Path node_modules)) { npm install }
npm run build
Pop-Location
$port = Get-KawanPort
Save-KawanPort $port
Write-Host "`nKawan is starting: open http://localhost:$port  (caregiver view: http://localhost:$port/caregiver)`n" -ForegroundColor Green
Set-Location backend
try {
  .\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port $port
} finally {
  Set-Location $PSScriptRoot
  if ((Get-SavedKawanPort) -eq $port) { Remove-Item $KawanPortFile -Force -ErrorAction SilentlyContinue }
}
