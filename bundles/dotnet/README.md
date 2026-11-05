# dotnet

The .NET SDK. **Opt-in**: no profile selects it, `dot apply dotnet`. macOS and Linux.

## Installs

| | how | latest via |
|---|---|---|
| Ubuntu | the newest `dotnet-sdk-N.M` in the **Ubuntu archive** (package pattern `dotnet-sdk-*`) | apt, after dot's refresh |
| macOS | cask `dotnet-sdk` | Homebrew |

`~/.dotnet/tools` goes on `PATH`: where `dotnet tool install -g` puts commands.

## Gotchas carried over

- **Not packages.microsoft.com.** Microsoft no longer publishes .NET for modern Ubuntu there:
  it ships in Ubuntu's own archive, and mixing the two feeds is a documented source of
  breakage (<https://learn.microsoft.com/en-us/dotnet/core/install/linux-ubuntu>).
- **The pattern is `dotnet-sdk-*`.** The archive also carries
  `dotnet-sdk-N.M-source-built-artifacts`, `dotnet-sdk-aot-N.M` and `dotnet-sdk-dbg-N.M`; dot
  ranks pattern matches by version and prefers a bare version to a longer name, so it picks
  `dotnet-sdk-10.0`. (The old script used the regex `^dotnet-sdk-[0-9]+\.[0-9]+$`.)
- A new major version is a new package name, so `dot apply` installs it when it appears in the
  archive; the old one stays until removed by hand (`apt remove dotnet-sdk-<old>`).
- **The cask is a `.pkg` installer**, not an app: it cannot be `--adopt`ed (dot knows) and runs
  `sudo installer`, so apply it from a terminal.
- This module used to run the **Go** installer on Linux by copy-paste, and the script it should
  have run pinned .NET 5 (EOL 2022) behind hardcoded download URLs that still resolved, so it
  would have installed an EOL runtime silently.
- The old zshrc set `DOTNET_ROOT=~/.dotnet` when that directory existed (the layout of
  Microsoft's `dotnet-install.sh`). Nothing here installs there: the Ubuntu package and the
  cask put the SDK where `dotnet` finds it without `DOTNET_ROOT`. Only `~/.dotnet/tools` is kept.
