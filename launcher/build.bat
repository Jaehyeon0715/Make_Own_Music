@echo off
REM Build single-file AI Composer tray launcher exe.
REM Output: dist\AIComposer.exe — copy to MOM\ to run.

setlocal
cd /d "%~dp0\.."

echo [1/4] Installing launcher dependencies...
python -m pip install -r launcher\requirements.txt || goto :err

echo [2/4] Generating icon...
python launcher\make_icon.py || goto :err

echo [3/4] Building exe with PyInstaller...
python -m PyInstaller ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --name AIComposer ^
  --icon launcher\icon.ico ^
  --paths . ^
  --collect-all pystray ^
  --collect-all PIL ^
  launcher\__main__.py || goto :err

echo [4/4] Done. Output: dist\AIComposer.exe
echo Move dist\AIComposer.exe to the MOM root for correct path resolution.
endlocal
exit /b 0

:err
echo Build failed.
endlocal
exit /b 1
