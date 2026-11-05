#!/bin/sh
# Installs (or replaces) ~/Applications/bb.app from bb's latest macOS disk image. ditto keeps
# the symlinks and signatures inside the bundle, which a zip unpack would not.
set -eu
app="$HOME/Applications/bb.app"
tmp=$(mktemp -d)
mnt="$tmp/mnt"
trap 'hdiutil detach "$mnt" -quiet >/dev/null 2>&1 || true; rm -rf "$tmp"' EXIT
curl -fsSL -o "$tmp/bb.dmg" https://getbb.app/download/macos
mkdir "$mnt"
hdiutil attach "$tmp/bb.dmg" -nobrowse -readonly -noverify -quiet -mountpoint "$mnt"
test -d "$mnt/bb.app" || { echo "bb.app is not in the disk image" >&2; exit 1; }
mkdir -p "$HOME/Applications"
rm -rf "$app.new"
ditto "$mnt/bb.app" "$app.new"
rm -rf "$app"
mv "$app.new" "$app"
