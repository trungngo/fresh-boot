#!/bin/sh
# Exits 0 when no JetBrains IDE is running, 1 when one is. JetBrains IDEs rewrite their
# options/*.xml on exit, so a running one would undo what the idea bundle writes there.
#
# Matches the launcher path: .../bin/idea (tarball, snap, Toolbox on Linux; also idea.sh),
# .../Contents/MacOS/idea (macOS), or a bare `idea` on PATH, for every product below, plus the
# classic JVM main class. The bracketed characters keep the pattern from matching the command
# line of a shell that spells it out (pgrep -f would otherwise find its own caller).
products='idea|pycharm|goland|rider|webstorm|clion|datagrip|dataspell|rustrover|phpstorm|rubymine|aqua|writerside'
if pgrep -if "(^|[/])($products)(64)?([.]sh)?( |\$)|com[.]intellij[.]idea[.]Main" >/dev/null 2>&1; then
    exit 1
fi
exit 0
