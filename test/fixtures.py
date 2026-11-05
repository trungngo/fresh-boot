#!/usr/bin/env python3
"""Local stand-in for the release APIs and downloads the bundles use, for sandbox applies
(test/converge.sh). Never touches the network; every artifact is a small stub made here.

    python3 test/fixtures.py <port>

Serves, on 127.0.0.1:<port>:
  /gh/repos/<owner>/<repo>/releases/latest     GitHub API (DOT_GITHUB_API=http://127.0.0.1:<port>/gh)
  /gl/projects/<id>/releases/permalink/latest  GitLab API (DOT_GITLAB_API=http://127.0.0.1:<port>/gl)
  /ghdl/..., /gldl/...                         the assets those releases list, which name them
                                               at https://github.com/ and https://gitlab.com/
                                               (DOT_URL_REWRITE sends those here: dot refuses
                                               a release asset that is not https)
  /gchrome/direct/google-chrome-stable_current_amd64.deb   Chrome (dl.google.com/linux)
  /zoom/client/latest/zoom_amd64.deb            Zoom (zoom.us)
  /discord/api/download                         Discord's .deb (discord.com)
  /dockerdesktop/linux/main/amd64/docker-desktop-amd64.deb   Docker Desktop (desktop.docker.com)
  /blob/cli/<name>                             devtunnel (DOT_URL_REWRITE https://tunnelsassetsprod...)
  /go/VERSION, /go/dl/<tarball>, /gosum/<tarball>.sha256   go.dev and its digests
  /jbdata/products/releases, /jbdl/toolbox/<tarball>[.sha256]
                                               JetBrains' release feed and downloads
                                               (data.services / download.jetbrains.com)

Release tags are fixed, so a second apply finds everything current.
"""
import hashlib
import http.server
import io
import json
import sys
import tarfile
import zipfile

PORT = int(sys.argv[1])


def stub(name):
    return f"#!/bin/sh\necho \"{name} $*\" >> \"${{FAKE_LOG:-/dev/null}}\"\n".encode()


def zip_of(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for path, data in files.items():
            info = zipfile.ZipInfo(path)
            info.external_attr = 0o755 << 16
            z.writestr(info, data)
    return buf.getvalue()


def tgz_of(files):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for path, data in files.items():
            info = tarfile.TarInfo(path)
            info.size = len(data)
            info.mode = 0o755
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


GO = "go1.99.0"
# repo -> (tag, {asset name: bytes})
RELEASES = {
    "Schniz/fnm": ("v9.9.9", {
        n: zip_of({"fnm": stub("fnm")}) for n in ("fnm-linux.zip", "fnm-arm64.zip", "fnm-macos.zip")
    }),
    "mkasberg/ghostty-ubuntu": ("2.0", {
        f"ghostty_2.0_{a}_{r}.deb": b"fake deb\n"
        for a in ("amd64", "arm64") for r in ("24.04", "25.10", "trixie", "forky")
    }),
    "zed-industries/zed": ("v9.9.9", {
        f"zed-linux-{a}.tar.gz": tgz_of({"zed.app/bin/zed": stub("zed"),
                                         "zed.app/libexec/zed-editor": stub("zed-editor")})
        for a in ("x86_64", "aarch64")
    }),
    "godotengine/godot": ("9.9-stable", {
        name: zip_of({name[:-4].replace("_mono_linux_", "_mono_linux."): stub("godot")})
        for name in ("Godot_v9.9-stable_linux.x86_64.zip", "Godot_v9.9-stable_linux.arm64.zip",
                     "Godot_v9.9-stable_mono_linux_x86_64.zip", "Godot_v9.9-stable_mono_linux_arm64.zip")
    }),
    "localsend/localsend": ("v9.9.9", {
        f"LocalSend-9.9.9-linux-{a}.deb": b"fake deb\n" for a in ("x86-64", "arm-64")
    }),
    "get-bb/bb": ("desktop-v9.9.9", {
        "bb-9.9.9-x86_64.AppImage": b"#!/bin/sh\necho bb\n",
        "bb-9.9.9-arm64.dmg": b"fake dmg\n",
    }),
    "IsmaelMartinez/teams-for-linux": ("v9.9.9", {
        f"teams-for-linux_9.9.9_{a}.deb": b"fake deb\n" for a in ("amd64", "arm64", "armv7l")
    }),
    "gitlab-org/cli": ("v9.9.9", {
        f"glab_9.9.9_linux_{a}.deb": b"fake deb\n" for a in ("amd64", "arm64")
    }),
    # starship (zsh bundle): the executable alone at the top of each tarball.
    "starship/starship": ("v9.9.9", {
        f"starship-{t}.tar.gz": tgz_of({"starship": stub("starship")})
        for t in ("x86_64-unknown-linux-musl", "aarch64-unknown-linux-musl",
                  "x86_64-apple-darwin", "aarch64-apple-darwin")
    }),
    # uv: <target>/uv and <target>/uvx in one tarball per target (musl decoys too).
    "astral-sh/uv": ("9.9.9", {
        f"uv-{t}.tar.gz": tgz_of({f"uv-{t}/uv": stub("uv"), f"uv-{t}/uvx": stub("uvx")})
        for t in ("x86_64-unknown-linux-gnu", "aarch64-unknown-linux-gnu",
                  "x86_64-unknown-linux-musl", "aarch64-unknown-linux-musl",
                  "x86_64-apple-darwin", "aarch64-apple-darwin")
    }),
    # codex: one executable named after the target per tarball, beside decoy assets the
    # bundle's explicit mapping must not pick (package, app-server, .zst).
    "openai/codex": ("rust-v9.9.9", {
        **{f"codex-{t}.tar.gz": tgz_of({f"codex-{t}": stub("codex")})
           for t in ("x86_64-unknown-linux-musl", "aarch64-unknown-linux-musl",
                     "x86_64-apple-darwin", "aarch64-apple-darwin")},
        **{f"codex-{k}-{t}.tar.gz": tgz_of({"bin/codex": stub(f"codex-{k}")})
           for k in ("package", "app-server") for t in ("x86_64-unknown-linux-musl", "aarch64-apple-darwin")},
        "codex-x86_64-unknown-linux-musl.zst": b"fake zst\n",
    }),
}
ASSETS = {name: data for _, (_, files) in RELEASES.items() for name, data in files.items()}
GO_TARBALLS = {f"{GO}.linux-{a}.tar.gz": tgz_of({"go/bin/go": stub("go"), "go/VERSION": GO.encode()})
               for a in ("amd64", "arm64")}
# JetBrains Toolbox (jetbrains-toolbox bundle): the release feed names the build, the tarball is
# jetbrains-toolbox-<build>/bin/..., with a `<digest> *<name>` .sha256 beside it.
TOOLBOX = "9.9.9.99999"
TOOLBOX_TARBALLS = {
    f"jetbrains-toolbox-{TOOLBOX}{s}.tar.gz": tgz_of({
        f"jetbrains-toolbox-{TOOLBOX}/bin/jetbrains-toolbox": stub("jetbrains-toolbox"),
        f"jetbrains-toolbox-{TOOLBOX}/bin/jetbrains-toolbox.desktop": b"[Desktop Entry]\n"})
    for s in ("", "-arm64")}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def github(repo):
    tag, files = RELEASES[repo]
    return {"tag_name": tag, "assets": [
        {"name": n, "browser_download_url": f"https://github.com/{repo}/releases/download/{tag}/{n}",
         "size": len(d), "digest": f"sha256:{sha(d)}"} for n, d in files.items()]}


def gitlab(repo):
    tag, files = RELEASES[repo]
    return {"tag_name": tag, "assets": {"links": [
        {"name": n, "url": f"https://gitlab.com/{repo}/-/releases/{tag}/downloads/{n}"}
        for n in files]}}


class Handler(http.server.BaseHTTPRequestHandler):
    def reply(self, body, ctype="application/octet-stream", code=200):
        if isinstance(body, (dict, list)):
            body, ctype = json.dumps(body).encode(), "application/json"
        elif isinstance(body, str):
            body, ctype = body.encode(), "text/plain"
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", f'"{sha(body)[:16]}"')
        self.send_header("Last-Modified", "Mon, 01 Jan 2024 00:00:00 GMT")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        p = self.path.split("?")[0]
        if p.startswith("/gh/repos/") and p.endswith("/releases/latest"):
            repo = p[len("/gh/repos/"):-len("/releases/latest")]
            return self.reply(github(repo)) if repo in RELEASES else self.reply("no such repo", code=404)
        if p.startswith("/gl/projects/") and p.endswith("/releases/permalink/latest"):
            repo = p[len("/gl/projects/"):-len("/releases/permalink/latest")].replace("%2F", "/")
            return self.reply(gitlab(repo)) if repo in RELEASES else self.reply("no such project", code=404)
        if p.startswith(("/ghdl/", "/gldl/")) and p.rsplit("/", 1)[1] in ASSETS:
            return self.reply(ASSETS[p.rsplit("/", 1)[1]])
        if p == "/gchrome/direct/google-chrome-stable_current_amd64.deb":
            return self.reply(b"fake deb\n")
        if p == "/zoom/client/latest/zoom_amd64.deb":
            return self.reply(b"fake deb\n")
        if p == "/discord/api/download":
            return self.reply(b"fake deb\n")
        if p == "/dockerdesktop/linux/main/amd64/docker-desktop-amd64.deb":
            return self.reply(b"fake deb\n")
        if p.startswith("/blob/cli/"):
            return self.reply(stub("devtunnel"))
        if p == "/go/VERSION":
            return self.reply(f"{GO}\ntime 2024-01-01T00:00:00Z\n")
        if p.startswith("/go/dl/") and p[7:] in GO_TARBALLS:
            return self.reply(GO_TARBALLS[p[7:]])
        if p.startswith("/gosum/") and p.endswith(".sha256") and p[7:-7] in GO_TARBALLS:
            return self.reply(sha(GO_TARBALLS[p[7:-7]]) + "\n")
        if p == "/jbdata/products/releases":
            dl = "https://download.jetbrains.com/toolbox"
            return self.reply({"TBA": [{"type": "release", "build": TOOLBOX, "downloads": {
                "linuxARM64": {"link": f"{dl}/jetbrains-toolbox-{TOOLBOX}-arm64.tar.gz"},
                "linux": {"link": f"{dl}/jetbrains-toolbox-{TOOLBOX}.tar.gz"}}}]})
        if p.startswith("/jbdl/toolbox/"):
            name = p[len("/jbdl/toolbox/"):]
            if name in TOOLBOX_TARBALLS:
                return self.reply(TOOLBOX_TARBALLS[name])
            if name.endswith(".sha256") and name[:-7] in TOOLBOX_TARBALLS:
                return self.reply(f"{sha(TOOLBOX_TARBALLS[name[:-7]])} *{name[:-7]}\n")
        self.reply("not found", code=404)

    def log_message(self, *args):
        pass


http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
