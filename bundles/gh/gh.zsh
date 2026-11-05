# gh bundle: GitHub CLI completion. Credentials live in the system keyring (`gh auth login`);
# no token is exported here: $GH_TOKEN would shadow every stored account and break
# `gh auth switch`.
if command -v gh >/dev/null; then
  eval "$(gh completion -s zsh)"
fi
