# python bundle: uv and uvx completions. Python itself needs no shell integration: uv puts
# python3 / python in ~/.local/bin (on PATH from `dot env`); no shims, no init.
if command -v uv >/dev/null; then
  eval "$(uv generate-shell-completion zsh)"
  eval "$(uvx --generate-shell-completion zsh)"
fi
