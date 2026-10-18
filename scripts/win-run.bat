@echo off
rem Run the pyguitest unit suite + the Windows torture-test driver from the
rem scratch tree. Launched through a Scheduled Task so it lands in the
rem interactive session: an SSH shell is Session 0 and sees no desktop, so
rem gui.windows() finds nothing there. py -u because buffered output makes a
rem working run look like a hang.
set PYTHONPATH=C:\Users\denni\tt-run
set TORTURE_APP_DIR=C:\Users\denni\tt-run
cd /d C:\Users\denni\tt-run
set LOG=C:\Users\denni\tt-run\run_0171.log

echo === started %DATE% %TIME% > %LOG%
py -u -c "import sys,pyguitest;print('interpreter',sys.version.split()[0]);print('pyguitest',pyguitest.__version__,pyguitest.__file__)" >> %LOG% 2>&1
py -u -c "import ctypes;print('session', ctypes.windll.kernel32.WTSGetActiveConsoleSessionId())" >> %LOG% 2>&1

echo === unit suite >> %LOG%
py -u -m pytest pyguitest-tests -q >> %LOG% 2>&1
echo unit-exit=%ERRORLEVEL% >> %LOG%

rem Sweep any torture-test app left from an earlier run before starting, and
rem again after. The driver closes the app it launches (windows.py's
rem close_all), but a run cut short -- a killed Scheduled Task, a timeout --
rem leaks a detached `pythonw -m torture_test` with no parent to reap it, and
rem it then sits on the interactive desktop indefinitely. This is the Windows
rem equivalent of run-box-tests.sh's `pkill -f "[t]orture_test"`; the sweep
rem lives in win-sweep.ps1 next to this file (inline PowerShell pipes do not
rem survive cmd's quoting), and is scoped to the torture_test command line so
rem it never touches an unrelated pythonw/python.
set SWEEP=powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0win-sweep.ps1"

echo === torture test >> %LOG%
%SWEEP% 2>nul
py -u windows.py >> %LOG% 2>&1
echo driver-exit=%ERRORLEVEL% >> %LOG%
%SWEEP% 2>nul
echo === finished %DATE% %TIME% >> %LOG%
