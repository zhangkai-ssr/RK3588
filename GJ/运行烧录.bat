@echo off
chcp 65001 >nul
echo ============================================
echo Orange Pi 5 Plus SD Card Flasher
echo ============================================
echo.
echo 请求管理员权限...
echo 如果弹出UAC窗口，请点击"是"
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -ArgumentList '-NoExit','-NoProfile','-ExecutionPolicy','Bypass','-File','C:\work1\JSZN\APRK3588\GJ\flash_sdcard.ps1' -Verb RunAs"

echo.
echo 已尝试启动管理员PowerShell窗口
echo 如果没有看到新窗口，可能是UAC被拒绝
echo.
pause
