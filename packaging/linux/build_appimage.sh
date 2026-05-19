#!/usr/bin/env bash
set -euo pipefail

BUNDLE_DIR="${1:?Bundle directory is required}"
OUTPUT_PATH="${2:?Output AppImage path is required}"
APPIMAGETOOL_PATH="${3:?Path to appimagetool is required}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
APPDIR="${ROOT_DIR}/build/linux-appimage/AppDir"
APP_LIB_DIR="${APPDIR}/usr/lib/FinAccountingApp"
APP_SHARE_DIR="${APPDIR}/usr/share"
ICON_SOURCE="${ROOT_DIR}/gui/assets/icons/app.png"
DESKTOP_SOURCE="${ROOT_DIR}/packaging/linux/FinAccountingApp.desktop"
APP_RUN_SOURCE="${ROOT_DIR}/packaging/linux/AppRun"
APP_BINARY="${BUNDLE_DIR}/FinAccountingApp"

if [[ ! -d "${BUNDLE_DIR}" ]]; then
  echo "Bundle directory not found: ${BUNDLE_DIR}" >&2
  exit 1
fi

if [[ ! -x "${APP_BINARY}" ]]; then
  echo "Expected Linux bundle executable not found or not executable: ${APP_BINARY}" >&2
  exit 1
fi

if [[ ! -f "${DESKTOP_SOURCE}" ]]; then
  echo "Desktop entry not found: ${DESKTOP_SOURCE}" >&2
  exit 1
fi

if [[ ! -f "${ICON_SOURCE}" ]]; then
  echo "Icon file not found: ${ICON_SOURCE}" >&2
  exit 1
fi

if [[ ! -f "${APP_RUN_SOURCE}" ]]; then
  echo "AppRun launcher not found: ${APP_RUN_SOURCE}" >&2
  exit 1
fi

if [[ ! -x "${APPIMAGETOOL_PATH}" ]]; then
  echo "appimagetool is missing or not executable: ${APPIMAGETOOL_PATH}" >&2
  exit 1
fi

rm -rf "${APPDIR}"
mkdir -p "${APP_LIB_DIR}" "${APP_SHARE_DIR}/applications" "${APP_SHARE_DIR}/icons/hicolor/256x256/apps"
mkdir -p "$(dirname "${OUTPUT_PATH}")"

cp -R "${BUNDLE_DIR}/." "${APP_LIB_DIR}/"
cp "${APP_RUN_SOURCE}" "${APPDIR}/AppRun"
cp "${DESKTOP_SOURCE}" "${APPDIR}/FinAccountingApp.desktop"
cp "${DESKTOP_SOURCE}" "${APP_SHARE_DIR}/applications/FinAccountingApp.desktop"
cp "${ICON_SOURCE}" "${APPDIR}/FinAccountingApp.png"
cp "${ICON_SOURCE}" "${APP_SHARE_DIR}/icons/hicolor/256x256/apps/FinAccountingApp.png"
chmod +x "${APPDIR}/AppRun"

"${APPIMAGETOOL_PATH}" --appimage-extract-and-run "${APPDIR}" "${OUTPUT_PATH}"
