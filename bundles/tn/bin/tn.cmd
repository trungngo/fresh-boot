@echo off
setlocal
if not defined TN_HOME set "TN_HOME=%USERPROFILE%\.local\share\tn"
rem An empty PYTHONPATH entry (the trailing ";" of "lib;" when none was set) is the current
rem directory, ahead of the standard library: -P would not keep a json.py there out.
if defined PYTHONPATH (
  set "PYTHONPATH=%TN_HOME%\lib;%PYTHONPATH%"
) else (
  set "PYTHONPATH=%TN_HOME%\lib"
)
rem Bytecode goes to the cache, never into %TN_HOME% (dot owns it), as bin/tn does.
if not defined PYTHONPYCACHEPREFIX (
  if defined XDG_CACHE_HOME (
    set "PYTHONPYCACHEPREFIX=%XDG_CACHE_HOME%\tn\pycache"
  ) else (
    set "PYTHONPYCACHEPREFIX=%USERPROFILE%\.cache\tn\pycache"
  )
)
rem -P: no current directory on sys.path, so a tn.py or tn\ where the user stands is not imported.
py -3 -P -m tn %*
exit /b %ERRORLEVEL%
