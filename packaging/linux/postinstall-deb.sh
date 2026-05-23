#!/bin/sh
set -eu

printf '%s\n' "deb" >/opt/Ledgera/.linux-package-kind || true

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q /usr/share/icons/hicolor || true
fi

if command -v appstreamcli >/dev/null 2>&1; then
  appstreamcli refresh-cache --force >/dev/null 2>&1 || true
fi
