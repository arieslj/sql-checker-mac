#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
icon_source="$PWD/assets/sql-checker-icon-v2.png"
iconset_path="$PWD/assets/AppIcon.iconset"
mkdir -p "$iconset_path"
for size in 16 32 128 256 512; do
    /usr/bin/sips -z "$size" "$size" "$icon_source" --out "$iconset_path/icon_${size}x${size}.png" >/dev/null
    retina_size=$((size * 2))
    /usr/bin/sips -z "$retina_size" "$retina_size" "$icon_source" --out "$iconset_path/icon_${size}x${size}@2x.png" >/dev/null
done
/usr/bin/iconutil -c icns "$iconset_path" -o "$PWD/assets/AppIcon.icns"
