#!/bin/bash

# Скрипт сборки drag-and-drop DMG для macOS:
# внутри образа: VirtualCom.app + ярлык Applications

set -euo pipefail

APP_NAME="VirtualCom"
BUILD_DIR="build_mac"
DIST_DIR="dist_mac"
DMG_CONTENT="dmg_content"
DMG_NAME="${APP_NAME}_Installer.dmg"
VENV_DIR="venv_mac"

CLI_BIN="${DIST_DIR}/${APP_NAME}"
APP_BUNDLE="${DIST_DIR}/${APP_NAME}.app"
APP_CONTENTS="${APP_BUNDLE}/Contents"
APP_MACOS="${APP_CONTENTS}/MacOS"
APP_RESOURCES="${APP_CONTENTS}/Resources"
BUNDLE_ICON_NAME="AppIcon.icns"
PROJECT_ICON_ICNS="assets/icons/virtualcom.icns"
PROJECT_ICON_PNG="assets/icons/virtualcom.png"

echo "🚀 Начинаем сборку ${APP_NAME} для macOS..."

# 1. Проверка Python
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ Ошибка: python3 не найден. Пожалуйста, установите Python 3."
    exit 1
fi

APP_VERSION="$(python3 - <<'PY'
import tomllib
with open("pyproject.toml", "rb") as f:
    data = tomllib.load(f)
print(data["project"]["version"])
PY
)"
RELEASE_DATE="$(python3 - <<'PY'
import tomllib
with open("pyproject.toml", "rb") as f:
    data = tomllib.load(f)
print(data.get("tool", {}).get("virtualcom", {}).get("release_date", ""))
PY
)"

echo "ℹ️ Версия сборки: ${APP_VERSION} (релиз: ${RELEASE_DATE})"

# 2. Создание и активация виртуального окружения
if [ ! -d "${VENV_DIR}" ]; then
    echo "📦 Создаем виртуальное окружение..."
    python3 -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"

# 3. Установка зависимостей
echo "⬇️  Устанавливаем зависимости..."
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

# 4. Сборка CLI-бинарника через PyInstaller
echo "🔨 Компиляция CLI-бинарника..."
pyinstaller --clean --noconfirm --onefile --console --name "${APP_NAME}" --distpath "${DIST_DIR}" --workpath "${BUILD_DIR}" vicom.py

if [ ! -f "${CLI_BIN}" ]; then
    echo "❌ Ошибка: бинарный файл не создан: ${CLI_BIN}"
    exit 1
fi

echo "✅ CLI-бинарник собран: ${CLI_BIN}"

# 5. Создание .app-обертки, которая запускает CLI в Terminal
echo "🧩 Создаем ${APP_NAME}.app..."
rm -rf "${APP_BUNDLE}"
mkdir -p "${APP_MACOS}" "${APP_RESOURCES}"

# Копируем сам CLI-бинарник в Resources
cp "${CLI_BIN}" "${APP_RESOURCES}/VirtualCom_bin"
chmod +x "${APP_RESOURCES}/VirtualCom_bin"

# Подхват иконки (приоритет):
# 1) ICON_SOURCE (если задан вручную)
# 2) Иконка из репозитория (assets/icons/virtualcom.icns)
# 3) Иконка из репозитория (assets/icons/virtualcom.png -> convert)
# 4) Иконка из существующего ViCom.app (fallback)
copy_icon_from_app_bundle() {
    local source_app="$1"
    local icon_name=""
    local icon_path=""

    if [ ! -d "${source_app}" ] || [ ! -f "${source_app}/Contents/Info.plist" ]; then
        return 1
    fi

    icon_name="$(/usr/libexec/PlistBuddy -c "Print :CFBundleIconFile" "${source_app}/Contents/Info.plist" 2>/dev/null || true)"
    if [ -z "${icon_name}" ]; then
        icon_name="AppIcon"
    fi
    case "${icon_name}" in
        *.icns) ;;
        *) icon_name="${icon_name}.icns" ;;
    esac

    icon_path="${source_app}/Contents/Resources/${icon_name}"
    if [ -f "${icon_path}" ]; then
        cp "${icon_path}" "${APP_RESOURCES}/${BUNDLE_ICON_NAME}"
        return 0
    fi

    return 1
}

convert_image_to_icns() {
    local source_image="$1"
    local out_icns="$2"
    local iconset_dir
    iconset_dir="$(mktemp -d)"
    iconset_dir="${iconset_dir}/icon.iconset"
    mkdir -p "${iconset_dir}"

    # Набор размеров для корректного отображения иконки в macOS
    sips -z 16 16   "${source_image}" --out "${iconset_dir}/icon_16x16.png" >/dev/null
    sips -z 32 32   "${source_image}" --out "${iconset_dir}/icon_16x16@2x.png" >/dev/null
    sips -z 32 32   "${source_image}" --out "${iconset_dir}/icon_32x32.png" >/dev/null
    sips -z 64 64   "${source_image}" --out "${iconset_dir}/icon_32x32@2x.png" >/dev/null
    sips -z 128 128 "${source_image}" --out "${iconset_dir}/icon_128x128.png" >/dev/null
    sips -z 256 256 "${source_image}" --out "${iconset_dir}/icon_128x128@2x.png" >/dev/null
    sips -z 256 256 "${source_image}" --out "${iconset_dir}/icon_256x256.png" >/dev/null
    sips -z 512 512 "${source_image}" --out "${iconset_dir}/icon_256x256@2x.png" >/dev/null
    sips -z 512 512 "${source_image}" --out "${iconset_dir}/icon_512x512.png" >/dev/null
    sips -z 1024 1024 "${source_image}" --out "${iconset_dir}/icon_512x512@2x.png" >/dev/null

    iconutil -c icns "${iconset_dir}" -o "${out_icns}"
    rm -rf "$(dirname "${iconset_dir}")"
}

ICON_SET=false
DESKTOP_DIR="${HOME}/Desktop"
ICON_SOURCE="${ICON_SOURCE:-}"

apply_icon_from_file() {
    local source_path="$1"
    local ext="${source_path##*.}"
    ext="$(printf '%s' "${ext}" | tr '[:upper:]' '[:lower:]')"

    if [ ! -e "${source_path}" ]; then
        return 1
    fi

    if [ -d "${source_path}" ]; then
        copy_icon_from_app_bundle "${source_path}"
        return $?
    fi

    if [ "${ext}" = "icns" ]; then
        cp "${source_path}" "${APP_RESOURCES}/${BUNDLE_ICON_NAME}"
        return 0
    fi

    if [ "${ext}" = "png" ] || [ "${ext}" = "jpg" ] || [ "${ext}" = "jpeg" ]; then
        convert_image_to_icns "${source_path}" "${APP_RESOURCES}/${BUNDLE_ICON_NAME}"
        return 0
    fi

    return 1
}

if [ -n "${ICON_SOURCE}" ] && apply_icon_from_file "${ICON_SOURCE}"; then
    ICON_SET=true
    echo "🎨 Иконка взята из ICON_SOURCE=${ICON_SOURCE}"
elif [ -f "${PROJECT_ICON_ICNS}" ]; then
    cp "${PROJECT_ICON_ICNS}" "${APP_RESOURCES}/${BUNDLE_ICON_NAME}"
    ICON_SET=true
    echo "🎨 Иконка взята из ${PROJECT_ICON_ICNS}"
elif [ -f "${PROJECT_ICON_PNG}" ]; then
    convert_image_to_icns "${PROJECT_ICON_PNG}" "${APP_RESOURCES}/${BUNDLE_ICON_NAME}"
    ICON_SET=true
    echo "🎨 Иконка сконвертирована из ${PROJECT_ICON_PNG}"
elif copy_icon_from_app_bundle "/Applications/ViCom.app"; then
    ICON_SET=true
    echo "🎨 Иконка взята из /Applications/ViCom.app"
elif copy_icon_from_app_bundle "${HOME}/Applications/ViCom.app"; then
    ICON_SET=true
    echo "🎨 Иконка взята из ${HOME}/Applications/ViCom.app"
elif copy_icon_from_app_bundle "${DESKTOP_DIR}/ViCom.app"; then
    ICON_SET=true
    echo "🎨 Иконка взята из ${DESKTOP_DIR}/ViCom.app"
elif copy_icon_from_app_bundle "${DESKTOP_DIR}/VirtualCom.app"; then
    ICON_SET=true
    echo "🎨 Иконка взята из ${DESKTOP_DIR}/VirtualCom.app"
elif [ -f "${DESKTOP_DIR}/ViCom.icns" ]; then
    cp "${DESKTOP_DIR}/ViCom.icns" "${APP_RESOURCES}/${BUNDLE_ICON_NAME}"
    ICON_SET=true
    echo "🎨 Иконка взята из ${DESKTOP_DIR}/ViCom.icns"
elif [ -f "${DESKTOP_DIR}/VirtualCom.icns" ]; then
    cp "${DESKTOP_DIR}/VirtualCom.icns" "${APP_RESOURCES}/${BUNDLE_ICON_NAME}"
    ICON_SET=true
    echo "🎨 Иконка взята из ${DESKTOP_DIR}/VirtualCom.icns"
else
    for candidate in "${DESKTOP_DIR}/ViCom.png" "${DESKTOP_DIR}/VirtualCom.png" "${DESKTOP_DIR}/ViCom.jpg" "${DESKTOP_DIR}/VirtualCom.jpg"; do
        if [ -f "${candidate}" ]; then
            convert_image_to_icns "${candidate}" "${APP_RESOURCES}/${BUNDLE_ICON_NAME}"
            ICON_SET=true
            echo "🎨 Иконка сконвертирована из ${candidate}"
            break
        fi
    done
fi

if [ "${ICON_SET}" = false ]; then
    echo "ℹ️ Иконка на рабочем столе не найдена, будет использована стандартная."
fi

# Launcher: двойной клик по .app открывает Terminal и запускает CLI
cat > "${APP_MACOS}/${APP_NAME}" <<'EOF'
#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BIN_PATH="${APP_ROOT}/Resources/VirtualCom_bin"

if [ ! -x "${BIN_PATH}" ]; then
  osascript -e 'display dialog "Не найден исполняемый файл VirtualCom_bin" buttons {"OK"} default button "OK" with icon stop'
  exit 1
fi

ESCAPED_CMD="$(printf '%q' "${BIN_PATH}")"
osascript <<APPLESCRIPT
tell application "Terminal"
    activate
    set targetTab to do script "${ESCAPED_CMD}; exit"
    repeat while busy of targetTab
        delay 1
    end repeat
end tell
APPLESCRIPT

# osascript выше блокирует launcher до завершения команды в Terminal,
# поэтому VirtualCom.app остается "живым" в Dock на время сессии.
EOF
chmod +x "${APP_MACOS}/${APP_NAME}"

# Info.plist для app bundle
cat > "${APP_CONTENTS}/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleDisplayName</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>com.virtualcom.app</string>
    <key>CFBundleVersion</key>
    <string>${APP_VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${APP_VERSION}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.13</string>
</dict>
</plist>
EOF

# 6. Создание DMG (VirtualCom.app + Applications)
echo "💿 Создаем DMG инсталлятор..."
rm -rf "${DMG_CONTENT}"
mkdir -p "${DMG_CONTENT}"
cp -R "${APP_BUNDLE}" "${DMG_CONTENT}/${APP_NAME}.app"

# Классический symlink для drag-and-drop установки
ln -s /Applications "${DMG_CONTENT}/Applications"

if [ -f "README.md" ]; then
    cp "README.md" "${DMG_CONTENT}/README.txt"
fi

rm -f "${DMG_NAME}"
hdiutil create -volname "${APP_NAME}" -srcfolder "${DMG_CONTENT}" -ov -format UDZO "${DMG_NAME}"

echo "🎉 Успешно! Инсталлятор создан: ${DMG_NAME}"
echo
echo "Для установки:"
echo "1. Откройте ${DMG_NAME}"
echo "2. Перетащите ${APP_NAME}.app на ярлык Applications"
echo "3. Запустите ${APP_NAME} из папки Applications"
