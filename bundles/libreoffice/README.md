# libreoffice

LibreOffice on an Ubuntu (or Debian) desktop (`family: debian, role: desktop`): Writer, Calc,
Impress, Draw, Base and Math. Selected by the desktop profiles; the bundle's `when` drops it on
macOS.

## Installs

| step | how |
|---|---|
| the suite | apt `libreoffice` (the metapackage for every component) |
| desktop integration | apt `libreoffice-gnome` (GTK 3 look, GIO file access for GNOME's network locations) |

## Why LibreOffice, from the archive

Apache OpenOffice is not packaged by Ubuntu or Debian: it is only offered as a tarball of `.deb`s
on SourceForge, with no apt repository and releases years apart. LibreOffice is the maintained fork
of the same code base, opens the same formats (`.odt`, `.ods`, `.odp`, and Microsoft Office's), and
is in the archive, so `dot apply --upgrade` keeps it current with everything else. The Document
Foundation's PPA and its own `.deb` tarballs track newer releases, but are not used (CLAUDE.md:
official sources, the package manager first); the snap and Flatpak builds are unofficial or
duplicate the archive.

## Gotchas

- **Ubuntu's "extended" install** already has LibreOffice; the default (minimal) install does not.
  Either way the step only installs what is missing.
- **libreoffice-gnome** is named explicitly because the metapackage lists it only as one of
  several alternative recommends (`libreoffice-gnome | libreoffice-plasma`); without it the UI
  falls back to the generic VCL look and cannot open `sftp://` / `smb://` locations from GNOME
  Files.
- **Large download** on a fresh machine: the metapackage pulls in every component plus its
  recommended fonts and extensions.
