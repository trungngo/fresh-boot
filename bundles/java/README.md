# java

The [Eclipse Temurin](https://adoptium.net) JDK (Adoptium), **current LTS**, from each
platform's package manager. macOS, Ubuntu and Windows (no profile selects it on Windows:
`dot apply java` there).

## Installs

| | source | package |
|---|---|---|
| Ubuntu | Adoptium's apt repository (`package_repo`, key pinned by fingerprint) | `temurin-25-jdk` |
| macOS | Homebrew cask | `temurin@25` |
| Windows | winget | `EclipseAdoptium.Temurin.25.JDK` |

`dot apply --upgrade` upgrades the JDK within the LTS line (25.0.x) with the package manager.

`java` is on `PATH` through each installer (update-alternatives on Ubuntu, `/usr/bin/java` on
macOS, the MSI's `PATH` entry on Windows). `java.zsh` (linked to `~/.config/zsh/conf.d/`) sets
`JAVA_HOME` for the tools that read it (Gradle, IDEs, Maven): `/usr/libexec/java_home` on macOS,
the JDK behind `javac` on Linux.

### Apt repository

`https://packages.adoptium.net/artifactory/deb`, suite `{{ codename }}`, component `main`,
signed by Adoptium's key (`https://packages.adoptium.net/artifactory/api/gpg/key/public`,
primary key `3B04 D753 C905 0D9A 5D34 3F39 843C 48A5 65F8 F04B`; dot refuses a key file holding
any other primary key). The keyring and sources names follow Adoptium's instructions
(`/etc/apt/keyrings/adoptium.asc`; their one-line `adoptium.list` is replaced by
`adoptium.sources`). Adoptium publishes a suite per supported codename and lags new Ubuntu
releases (questing has none yet): `fallback_suite: noble` serves those.

## Gotchas

- **The one version number in this repo.** Every channel puts the major version in the
  package ID (`temurin-25-jdk`, `temurin@25`, `EclipseAdoptium.Temurin.25.JDK`). The
  unversioned alternatives track the newest *feature* release, not the LTS: the apt repository
  carries `temurin-26-jdk`, `temurin-27-jdk`, ... (a `temurin-*-jdk` pattern would pick those)
  and the bare `temurin` cask is 27. When the next LTS ships (every two years, in September;
  the one after 25 is 29), change the three IDs together.
- **The cask is a `.pkg`** (it runs `sudo installer`), so it cannot be `--adopt`ed and needs a
  terminal for the password (the `cask-pkg-sudo` hint).
- A project that needs another JDK: install it next to this one (`temurin-21-jdk`,
  `temurin@21`) and pick it with `JAVA_HOME` or the build tool's toolchains; Gradle and Maven
  toolchains find JDKs under `/usr/lib/jvm` and `/Library/Java/JavaVirtualMachines`.
- **No SDKMAN.** The old setup (and this repo's first port) installed the JDK with SDKMAN's
  `curl | bash` installer, which needed `?rcupdate=false`, an `sdk` shell-function prelude and
  `set +eu`. It is gone, and so is the sdkman bundle. The step "Retire the SDKMAN shell
  integration" removes the old `~/.config/zsh/conf.d/sdkman.zsh` link (only a link). `~/.sdkman`
  itself and the `SDKMAN_DIR` it left in `dot env` state are not touched: `rm -rf ~/.sdkman` by
  hand; `dot status` lists the old sdkman records as orphans until then.
