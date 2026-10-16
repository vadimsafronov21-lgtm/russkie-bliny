param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Сначала выполните установку из README.md.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) { throw 'Сначала соберите frontend: pnpm run build.' }
& $pythonPath -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Ошибка миграции.' }
& $pythonPath -m backend.app.seed
if ($LASTEXITCODE -ne 0) { throw 'Ошибка подготовки demo-данных.' }
Write-Host "Приложение: http://127.0.0.1:$Port. Для остановки нажмите Ctrl+C. Worker запускается отдельно."
& $pythonPath -m uvicorn backend.app.main:app --host 127.0.0.1 --port $Port
