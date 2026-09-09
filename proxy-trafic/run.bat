@echo off
:loop
for /L %%i in (1,1,30) do start "" python human-visit-proxy-coord-click.py yes
timeout /t 1500 /nobreak >nul
goto loop