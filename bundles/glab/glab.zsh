# glab bundle: GitLab CLI completion. No token is exported: the login is glab's own
# (`glab auth login`, run by hand), and GITLAB_TOKEN must stay unset (even empty, it
# shadows the gitlab.com keyring login -> 401).
command -v glab >/dev/null && eval "$(glab completion -s zsh)"
