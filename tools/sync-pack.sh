#!/bin/bash
# Copy the OmaPixIcon pack this plugin ships from an OmaPixIcon checkout.
set -euo pipefail
src=${1:?usage: tools/sync-pack.sh <OmaPixIcon checkout>}
dst="$(cd "$(dirname "$0")/.." && pwd)/pack"
[[ -z $(git -C "$src" status --porcelain -- engine/render.py data) ]] || { echo "commit the pack in $src first" >&2; exit 1; }
rm -rf "$dst" && mkdir -p "$dst/engine" "$dst/data"
cp "$src/engine/render.py" "$dst/engine/"
cp "$src/data/icons.json" "$src/data/omarchy-themes.json" "$dst/data/"
cp "$src/LICENSE" "$dst/"
git -C "$src" rev-parse HEAD >"$dst/SOURCE"
echo "pack synced from OmaPixIcon $(cat "$dst/SOURCE")"
