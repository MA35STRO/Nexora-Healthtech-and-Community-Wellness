# One-command start (Windows): installs what's missing, builds the dashboard, runs everything on http://localhost:8000
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path backend\.venv)) {
  Write-Host 'Creating Python environment...'
  if (Get-Command uv -ErrorAction SilentlyContinue) { uv venv --python 3.12 backend\.venv; uv pip install --python backend\.venv\Scripts\python.exe -r backend\requirements.txt }
  else { py -3.12 -m venv backend\.venv; backend\.venv\Scripts\python -m pip install -r backend\requirements.txt }
}
Push-Location frontend
if (-not (Test-Path node_modules)) { npm install }
npm run build
Pop-Location
Write-Host "`nBAYMAX is starting: open http://localhost:8000  (caregiver view: /caregiver)`n" -ForegroundColor Green
Set-Location backend
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
