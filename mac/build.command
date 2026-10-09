#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYINSTALLER_CONFIG_DIR="$PWD/mac/.pyinstaller-cache"
export CLANG_MODULE_CACHE_PATH="$PWD/mac/.swift-cache"
.venv/bin/python -m PyInstaller --noconfirm --clean --log-level WARN --onedir --name SQLCheckerBackend --distpath mac/build-backend --workpath mac/build-work --specpath mac --add-data "$PWD/static:static" --collect-all sqlfluff --collect-all sqlglot --copy-metadata sqlfluff --copy-metadata sqlglot mac_backend.py
app_path="$PWD/mac/dist/SQL 检查器.app"
mkdir -p "$app_path/Contents/MacOS" "$app_path/Contents/Resources/backend"
cp -R mac/build-backend/SQLCheckerBackend "$app_path/Contents/Resources/backend/"
xcrun swiftc mac/main.swift -o "$app_path/Contents/MacOS/SQLChecker" -framework Cocoa -framework WebKit -module-cache-path "$PWD/mac/.swift-cache"
bash mac/make-icon.command
cp mac/assets/AppIcon.icns "$app_path/Contents/Resources/AppIcon.icns"
.venv/bin/python mac/prepare-ui.py "$app_path/Contents/Resources/ui"
cp mac/Info.plist "$app_path/Contents/Info.plist"
cp -R third_party_licenses "$app_path/Contents/Resources/ThirdPartyLicenses"
/usr/bin/codesign --force --deep --sign - "$app_path"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$app_path" mac/SQL-Checker-macOS-AppleSilicon-v1.0.3.zip
echo "打包完成：$app_path"
