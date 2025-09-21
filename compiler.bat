python -m PyInstaller --onefile --distpath . --name ytd --add-data "src/yt-dlp.exe;src" --add-data "src/ffmpeg.exe;src" ytd.py
del ytd.spec
rmdir /s /q build
