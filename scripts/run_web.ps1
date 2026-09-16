# 任务11 · 一键启动前端（Streamlit）
# 用法：powershell -ExecutionPolicy Bypass -File scripts/run_web.ps1 [-Port 8501] [-Api http://127.0.0.1:8000]
param(
    [int]$Port = 8501,
    [string]$Api = "http://127.0.0.1:8000"
)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$env:API_BASE = $Api
Write-Host "启动 Streamlit 前端 …" -ForegroundColor Cyan
Write-Host "  页面地址： http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "  后端地址： $Api   （若未启动后端，请另开终端跑 scripts/run_api.ps1）" -ForegroundColor DarkGray

python -m streamlit run src/web/app.py --server.port $Port --server.address 127.0.0.1 `
    --browser.gatherUsageStats false
