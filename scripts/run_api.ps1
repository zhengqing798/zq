# 任务11 · 一键启动后端（FastAPI）
# 用法：powershell -ExecutionPolicy Bypass -File scripts/run_api.ps1 [-Port 8000] [-Reload]
param(
    [int]$Port = 8000,
    [string]$Host_ = "127.0.0.1",
    [switch]$Reload
)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "启动 FastAPI 后端 …" -ForegroundColor Cyan
Write-Host "  接口文档： http://${Host_}:$Port/docs" -ForegroundColor Green
Write-Host "  健康检查： http://${Host_}:$Port/api/health" -ForegroundColor Green
Write-Host "  首次启动会预加载匹配引擎与检索索引（约 10 秒），请耐心等待。" -ForegroundColor DarkGray

$args = @("-m", "uvicorn", "src.api.main:app", "--host", $Host_, "--port", "$Port")
if ($Reload) { $args += "--reload" }
python @args
