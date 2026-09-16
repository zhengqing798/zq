# 任务11 · 一键启动 Vue3 前端（答辩主秀版）
# 用法：powershell -ExecutionPolicy Bypass -File scripts/run_web_vue.ps1 [-Port 5173]
# 前置：已装 Node 18+；先在另一个终端跑 scripts/run_api.ps1 启动后端（8000）
param(
    [int]$Port = 5173,
    [string]$Api = "http://127.0.0.1:8000"
)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\web")

if (-not (Test-Path "node_modules")) {
    Write-Host "首次运行，正在安装依赖（已配 npmmirror 源）…" -ForegroundColor Yellow
    npm install
}

$env:VITE_API_BASE = ""
Write-Host "启动 Vue3 前端（Vite）…" -ForegroundColor Cyan
Write-Host "  页面地址： http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "  接口代理： /api -> $Api   （由 vite.config.ts 配置；后端未启动时页面会提示）" -ForegroundColor DarkGray

npm run dev -- --port $Port
