#!/bin/sh
set -eu
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
"$DIR/.venv/bin/python" "$DIR/scripts/patch_aero_gui_macos.py" >/dev/null
exec "$DIR/.venv/bin/aero-open-gui" "$@"
