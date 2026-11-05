# java bundle: JAVA_HOME for tools that read it (Gradle, IDEs, Maven prefers it). `java` itself
# is on PATH already. macOS: java_home picks the newest installed JDK (the Temurin cask's);
# Linux: the JDK that update-alternatives made `javac`.
if [[ -x /usr/libexec/java_home ]]; then
  JAVA_HOME=$(/usr/libexec/java_home 2>/dev/null) && export JAVA_HOME || unset JAVA_HOME
elif (( $+commands[javac] )); then
  export JAVA_HOME=${${commands[javac]:A}%/bin/javac}
fi
