# Kill any leftover torture-test app process, scoped to its command line so an
# unrelated pythonw/python is never touched. Called by win-run.bat before and
# after the driver run -- the Windows equivalent of run-box-tests.sh's
# `pkill -f "[t]orture_test"`, for the case a run is cut short before the
# driver's own close_all reaps the detached `pythonw -m torture_test` it
# launched. A clean no-op when nothing matches.
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*torture_test*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
