# New Windows machine (PowerShell 5.1 or 7): Git, this repository in ~\.dot, dot, then
# `dot apply`. Copy this file, or paste it into PowerShell; extra arguments go to `dot apply`.
# winget ships with Windows 11 (App Installer on Windows 10).
$ErrorActionPreference = 'Stop'

function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'User')
}

# Runs a native command and returns its output as text; $LASTEXITCODE holds its exit code.
# 'Stop' would turn its stderr into a terminating error in Windows PowerShell 5.1.
function Invoke-Quiet([scriptblock]$Command) {
    $eap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { (& $Command 2>&1 | Out-String) } finally { $ErrorActionPreference = $eap }
}

# 1. Git, from the winget source only: searching msstore too fails where TLS
# is inspected ("The server certificate did not match any of the expected values").
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements }
# dot.exe links the Visual C++ runtime (vcruntime140.dll), which a fresh Windows may lack:
# without it dot exits at once, printing nothing.
if (-not (Test-Path (Join-Path $env:windir 'System32\vcruntime140.dll'))) {
    $vcArch = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'x64' }
    winget install --id "Microsoft.VCRedist.2015+.$vcArch" -e --source winget --accept-source-agreements --accept-package-agreements
}
Refresh-Path

# 2. This repository (public: no login), then dot from its public release, then apply.
$repo = Join-Path $HOME '.dot'
$url = if ($env:FRESH_BOOT_REPO) { $env:FRESH_BOOT_REPO } else { 'https://github.com/trungngo/fresh-boot.git' }
if (-not (Test-Path (Join-Path $repo '.git'))) { git clone $url $repo }

$dotBin = Join-Path $env:LOCALAPPDATA 'Programs\dot'
if (-not (Get-Command dot -ErrorAction SilentlyContinue) -and -not (Test-Path (Join-Path $dotBin 'dot.exe'))) {
    iwr -useb https://raw.githubusercontent.com/trungngo/dot-cli/main/install.ps1 | iex
}
$env:Path = "$dotBin;$env:Path"

# dot's own installer adds its folder to the user's PATH, but it is skipped when dot.exe is
# already there (an earlier or partial run), and then new terminals never find `dot`. Make sure
# the user's PATH has it. Read and written raw (REG_EXPAND_SZ), so %VAR% entries stay unexpanded.
if (Test-Path (Join-Path $dotBin 'dot.exe')) {
    $envKey = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Environment')
    try {
        $userPath = [string]$envKey.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        $entries = @(if ($userPath) { $userPath -split ';' | Where-Object { $_ } } else { @() })
        if (@($entries | Where-Object { $_.TrimEnd('\') -ieq $dotBin }).Count -eq 0) {
            $envKey.SetValue('Path', ((@($entries) + $dotBin) -join ';'), [Microsoft.Win32.RegistryValueKind]::ExpandString)
            # Tell running programs (Explorer, new terminals) that the environment changed.
            [Environment]::SetEnvironmentVariable('FRESH_BOOT_PATH_CHANGED', '1', 'User')
            [Environment]::SetEnvironmentVariable('FRESH_BOOT_PATH_CHANGED', $null, 'User')
            Write-Host "fresh-boot: added $dotBin to your PATH (open a new terminal to use dot)"
        }
    } finally { $envKey.Close() }
}

dot apply @args
