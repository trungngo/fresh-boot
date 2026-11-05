# glab bundle: GitLab CLI completion. No token is exported: the login is in glab's own store
# (keyring), put there by `dot apply glab`, and GITLAB_TOKEN must stay unset (even empty, it
# shadows the gitlab.com keyring login -> 401).
command -v glab >/dev/null && eval "$(glab completion -s zsh)"
