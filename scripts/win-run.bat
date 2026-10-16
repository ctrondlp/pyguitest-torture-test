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

echo === torture test >> %LOG%
py -u windows.py >> %LOG% 2>&1
echo driver-exit=%ERRORLEVEL% >> %LOG%
echo === finished %DATE% %TIME% >> %LOG%
