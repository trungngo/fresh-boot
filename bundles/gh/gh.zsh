# gh bundle: GitHub CLI completion. Credentials live in the system keyring (`gh auth login`);
# no token is exported here: $GH_TOKEN would shadow every stored account and break
# `gh auth switch`. Cached by zshrc (zshrc_cached): generating it takes gh a third of a second.
zshrc_cached gh completion -s zsh && source "$REPLY"
