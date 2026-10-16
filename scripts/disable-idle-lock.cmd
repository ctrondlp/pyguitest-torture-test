@echo off
rem Stop the Windows test box from locking, blanking or sleeping while a
rem driver runs. Run once from an interactive (console/RDP) session as the
rem desktop user; the HKLM line needs an elevated prompt and is skipped
rem otherwise. Idempotent. The Unix boxes use scripts/disable-idle-lock.sh.

echo Power plan: monitor off / standby / hibernate = never (AC and DC)
powercfg /change monitor-timeout-ac 0
powercfg /change monitor-timeout-dc 0
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
powercfg /change hibernate-timeout-ac 0
powercfg /change hibernate-timeout-dc 0

echo Screen saver: off, and no password on resume
reg add "HKCU\Control Panel\Desktop" /v ScreenSaveActive /t REG_SZ /d 0 /f >nul
reg add "HKCU\Control Panel\Desktop" /v ScreenSaverIsSecure /t REG_SZ /d 0 /f >nul
reg delete "HKCU\Control Panel\Desktop" /v SCRNSAVE.EXE /f >nul 2>&1

echo Dynamic lock (phone-proximity lock): off
reg add "HKCU\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v EnableGoodbye /t REG_DWORD /d 0 /f >nul

echo Machine inactivity limit (needs admin; skipped if not elevated)
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v InactivityTimeoutSecs /t REG_DWORD /d 0 /f >nul 2>&1 && echo   InactivityTimeoutSecs = 0 || echo   not elevated, InactivityTimeoutSecs left alone

echo.
echo Now:
powercfg /query SCHEME_CURRENT SUB_VIDEO VIDEOIDLE | findstr /i "Current AC Power Setting Index"
reg query "HKCU\Control Panel\Desktop" /v ScreenSaveActive | findstr ScreenSaveActive
