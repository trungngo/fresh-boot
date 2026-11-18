# python bundle: uv and uvx completions. Python itself needs no shell integration: uv puts
# python3 / python in ~/.local/bin (on PATH from `dot env`); no shims, no init. Generated once
# per uv / uvx release by zshrc_cached (zshrc) and autoloaded on the first completion: uv's is
# half a megabyte, which took a third of a second to parse at every shell start.
if zshrc_cached --as _uv uv generate-shell-completion zsh; then
  fpath+=("${REPLY:h}"); autoload -Uz _uv && compdef _uv uv
fi
if zshrc_cached --as _uvx uvx --generate-shell-completion zsh; then
  fpath+=("${REPLY:h}"); autoload -Uz _uvx && compdef _uvx uvx
fi
