@echo off
rem ============================================================
rem  一键推送到 GitHub（网络恢复后双击运行即可）
rem  用法: 双击本文件 或 在命令行执行 scripts\push-to-github.bat
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0\.."
echo [1/3] 查看待提交改动...
git status --short
echo.
echo [2/3] 推送到远程 origin/main ...
git push -u origin main
if errorlevel 1 (
    echo.
    echo [失败] 推送未完成。常见原因：
    echo   1) 网络无法访问 github.com（可换教室网络/手机热点/VPN 后重试）
    echo   2) 首次推送需登录：会弹出 GitHub 登录窗口，选 "Sign in with your browser"
    echo      或用 Token: Settings - Developer settings - Personal access tokens
    echo      生成后用户名填 zhengqing798, 密码粘贴 Token
    echo   3) 本地还有未提交改动，先执行: git add . 和 git commit -m "说明"
) else (
    echo.
    echo [成功] 已推送到 https://github.com/zhengqing798/zq
)
echo.
pause
