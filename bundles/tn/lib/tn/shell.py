"""``tn shell init zsh|bash|pwsh`` (spec §6.7): the cd wrapper function and completion."""

from __future__ import annotations

SHELLS = ("zsh", "bash", "pwsh")

_POSIX_FUNCTION = r'''tn() {
  local __tn_f __tn_rc
  __tn_f="$(mktemp "${TMPDIR:-/tmp}/tn-cd.XXXXXX")" || { command tn "$@"; return; }
  TN_CD_FILE="$__tn_f" TN_SHELL=1 command tn "$@"; __tn_rc=$?
  if [ -s "$__tn_f" ]; then builtin cd -- "$(cat -- "$__tn_f")" || __tn_rc=1; fi
  rm -f -- "$__tn_f"
  return $__tn_rc
}
'''

_ZSH_COMPLETION = r'''_tn() {
  local -a __tn_lines __tn_vals
  local __tn_l __tn_v __tn_d
  __tn_lines=("${(@f)$(command tn __complete $((CURRENT-1)) -- "${words[@]}" 2>/dev/null)}")
  for __tn_l in "${__tn_lines[@]}"; do
    [[ -z "$__tn_l" ]] && continue
    case "$__tn_l" in
      __tn_files__) _files; return ;;
      __tn_dirs__) _files -/; return ;;
    esac
    __tn_v="${__tn_l%%$'\t'*}"
    __tn_v="${__tn_v//:/\\:}"
    if [[ "$__tn_l" == *$'\t'* ]]; then
      __tn_d="${__tn_l#*$'\t'}"
      __tn_vals+=("$__tn_v:$__tn_d")
    else
      __tn_vals+=("$__tn_v")
    fi
  done
  (( ${#__tn_vals} )) && _describe -t tn 'tn' __tn_vals
}
if (( $+functions[compdef] )); then compdef _tn tn; fi
'''

_BASH_COMPLETION = r'''_tn() {
  local IFS=$'\n' __tn_l
  local -a __tn_out
  __tn_out=($(command tn __complete "$COMP_CWORD" -- "${COMP_WORDS[@]}" 2>/dev/null))
  COMPREPLY=()
  for __tn_l in "${__tn_out[@]}"; do
    case "$__tn_l" in __tn_files__|__tn_dirs__) continue ;; esac
    COMPREPLY+=("${__tn_l%%$'\t'*}")
  done
}
complete -o default -F _tn tn
'''

# PowerShell's binder drops a bare `--` given to a function, so `tn run prod -- tail -n 5`
# would reach tn as `run prod tail -n 5` (and -n would be --dry-run). __tn_args puts it back:
# it re-parses the invocation line and, when the call has exactly one element more than $args
# and that element is `--`, inserts `--` at its place. Anything it cannot line up (splatting,
# several tn calls on one line it cannot tell apart) is passed on unchanged; quoting '--'
# always works. tn prints UTF-8 (tn.cli.utf8_stdio): the console encoding is set to match
# while tn runs, so captured output (ConvertFrom-Json, completion) is decoded correctly.
_PWSH = r'''function __tn_args($inv, $a) {
  $a = @($a)
  try {
    $line = $inv.Line
    if (-not $line -or -not $line.Contains('--')) { return ,$a }
    $ast = [System.Management.Automation.Language.Parser]::ParseInput($line, [ref]$null, [ref]$null)
    $col = $inv.OffsetInLine
    $cmd = $ast.FindAll({ param($n)
        $n -is [System.Management.Automation.Language.CommandAst] -and
        $n.Extent.StartColumnNumber -eq $col }, $true) | Select-Object -First 1
    if (-not $cmd) { return ,$a }
    $els = @($cmd.CommandElements | Select-Object -Skip 1)
    if ($els.Count -ne $a.Count + 1) { return ,$a }
    for ($i = 0; $i -lt $els.Count; $i++) {
      if ($els[$i].Extent.Text -eq '--') {
        return ,(@($a | Select-Object -First $i) + @('--') + @($a | Select-Object -Skip $i))
      }
    }
  } catch { }
  return ,$a
}

function tn {
  $f = [IO.Path]::GetTempFileName()
  $exe = (Get-Command tn.cmd -CommandType Application | Select-Object -First 1).Source
  $tnArgs = __tn_args $MyInvocation $args
  $enc = $null
  try {
    $enc = [Console]::OutputEncoding
    [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
  } catch { }
  try {
    $env:TN_CD_FILE = $f; $env:TN_SHELL = '1'
    & $exe @tnArgs; $rc = $LASTEXITCODE
    $p = (Get-Content -Raw -LiteralPath $f); if ($p) { Set-Location -LiteralPath $p.Trim() }
  } finally {
    if ($enc) { try { [Console]::OutputEncoding = $enc } catch { } }
    Remove-Item -LiteralPath $f -ErrorAction Ignore
    Remove-Item Env:TN_CD_FILE, Env:TN_SHELL -ErrorAction Ignore
  }
  $global:LASTEXITCODE = $rc
}

Register-ArgumentCompleter -Native -CommandName tn,tn.cmd -ScriptBlock {
  param($wordToComplete, $commandAst, $cursorPosition)
  $words = @($commandAst.CommandElements | ForEach-Object { $_.ToString() })
  if ($wordToComplete -eq '') { $words += '' }
  $cword = $words.Count - 1
  $exe = (Get-Command tn.cmd -CommandType Application | Select-Object -First 1).Source
  $enc = $null
  try {
    $enc = [Console]::OutputEncoding
    [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
  } catch { }
  $lines = @(& $exe __complete $cword -- @words 2>$null)
  if ($enc) { try { [Console]::OutputEncoding = $enc } catch { } }
  $lines | ForEach-Object {
    $v, $d = $_ -split "`t", 2
    if ($v -and $v -notlike '__tn_*__') {
      if (-not $d) { $d = $v }
      [System.Management.Automation.CompletionResult]::new($v, $v, 'ParameterValue', $d)
    }
  }
}
'''


def init_fix(windows: bool) -> str:
    """The line a shell profile needs for the tn function (doctor's fix, request_cd's hint)."""
    if windows:
        return "tn shell init pwsh | Out-String | Invoke-Expression"
    return 'eval "$(tn shell init zsh)"'


def script(shell: str) -> str:
    if shell == "zsh":
        return _POSIX_FUNCTION + "\n" + _ZSH_COMPLETION
    if shell == "bash":
        return _POSIX_FUNCTION + "\n" + _BASH_COMPLETION
    if shell == "pwsh":
        return _PWSH
    raise ValueError(shell)
