@echo off
REM ===============================
REM Stability Matrix A1111 + SD GUI タスクトレイ起動
REM ===============================

REM 1. WebUI(A1111)ディレクトリに移動
cd /d "C:\StabilityMatrix\Packages\Stable Diffusion WebUI"

REM 2. WebUI を API モードで起動（別ウィンドウ）
start cmd /k python launch.py --listen --api

REM 3. WebUI API 起動確認の待機（簡易版）
echo WebUI API の起動を待機中...
:waitloop
powershell -Command ^
try { ^
  $resp = Invoke-WebRequest -Uri "http://127.0.0.1:7860/sdapi/v1/sd-models" -UseBasicParsing; ^
  if ($resp.StatusCode -eq 200) { exit 0 } else { exit 1 } ^
} catch { exit 1 } 
if %ERRORLEVEL% NEQ 0 (
    timeout /t 2 >nul
    goto waitloop
)
echo API 起動完了

REM 4. タスクトレイ常駐版 Python GUI を起動
cd /d "C:\Path\To\Your\PythonScript"
start "" python sd_gui_tray.py

echo WebUI + SD GUI タスクトレイ常駐版の起動を開始しました。
