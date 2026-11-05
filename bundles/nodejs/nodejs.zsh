# nodejs bundle: fnm's shell integration. --use-on-cd switches Node on `cd` into a directory
# with .nvmrc / .node-version, like nvm did. fnm itself is on PATH (~/.local/bin or brew).
command -v fnm >/dev/null && eval "$(fnm env --use-on-cd --shell zsh)"
