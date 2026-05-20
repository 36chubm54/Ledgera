#!/usr/bin/env bash
set -euo pipefail

BUNDLE_DIR="${1:?Bundle directory is required}"
OUTPUT_DIR="${2:?Output directory is required}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
STAGING_DIR="${ROOT_DIR}/build/linux-packages"
ENV_FILE="${STAGING_DIR}/package.env"
NFPM_CONFIG="${STAGING_DIR}/nfpm.generated.yaml"

if [[ ! -d "${BUNDLE_DIR}" ]]; then
  echo "Bundle directory not found: ${BUNDLE_DIR}" >&2
  exit 1
fi

if ! command -v nfpm >/dev/null 2>&1; then
  echo "nfpm is not installed or not on PATH" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"

python "${ROOT_DIR}/packaging/linux/build_system_packages.py" \
  --bundle-dir "${BUNDLE_DIR}" \
  --staging-dir "${STAGING_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Package env file not found: ${ENV_FILE}" >&2
  exit 1
fi

if [[ ! -f "${NFPM_CONFIG}" ]]; then
  echo "Rendered nFPM config file not found: ${NFPM_CONFIG}" >&2
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

nfpm package \
  --packager deb \
  --config "${NFPM_CONFIG}" \
  --target "${OUTPUT_DIR}/FinAccountingApp-${PACKAGE_VERSION}-x86_64.deb"

nfpm package \
  --packager rpm \
  --config "${NFPM_CONFIG}" \
  --target "${OUTPUT_DIR}/FinAccountingApp-${PACKAGE_VERSION}-x86_64.rpm"
