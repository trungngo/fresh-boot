# maven

[Apache Maven](https://maven.apache.org) from the package manager. **Opt-in**: no profile
selects it, `dot apply maven`. macOS and Linux.

## Installs

| | Maven |
|---|---|
| Ubuntu | `maven` (Ubuntu's archive) |
| macOS | `maven` (Homebrew formula) |

`dot apply --upgrade` upgrades it with the rest of the package manager's packages; nothing is
pinned. It `requires: [java]`, so the [Temurin JDK](../java/README.md) is installed first.

## Gotchas

- **Why `requires: [java]`.** Ubuntu's `maven` depends on `default-jre-headless` or any package
  providing `java-runtime-headless`. With Temurin installed first (it provides that), apt is
  satisfied; installed on its own, apt would pull in OpenJDK as a second JDK.
- **Homebrew's `maven` depends on the `openjdk` formula** and installs it whatever else is
  there; `mvn` still runs on `JAVA_HOME` when it is set, which the java bundle's `java.zsh` sets
  to the Temurin JDK (`/usr/libexec/java_home`), so builds use Temurin.
- Ubuntu's archive trails Maven releases (it ships the version current at the Ubuntu release).
  A project that needs a newer one uses the Maven Wrapper (`mvn wrapper:wrapper`, then
  `./mvnw`), which is the usual practice anyway.
- The old setup installed Maven through SDKMAN (`sdk install maven`); SDKMAN is gone (see the
  [java](../java/README.md) bundle). `~/.sdkman` from an earlier setup is not removed.
