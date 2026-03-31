@echo off
echo Building TwitterArchiver.exe ...
python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name TwitterArchiver ^
    --add-data "viewer.html;." ^
    gui.py
echo.
echo Done. Check dist\TwitterArchiver.exe
pause
