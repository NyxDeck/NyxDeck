#!/usr/bin/env bash
# Start DankMaterialShell for the niri session.
#
# DMS runs in an app scope that can outlive niri.service, like most
# quickshell-based shells. Clear any scope leaked by the previous session
# before attaching a fresh instance.
set -u

systemctl --user stop 'app-niri-dms-*.scope' >/dev/null 2>&1 || true
exec dms run
