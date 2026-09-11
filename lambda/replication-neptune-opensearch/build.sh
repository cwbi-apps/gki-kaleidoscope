#!/usr/bin/env bash
set -euo pipefail

# Builds function.zip for the Neptune -> OpenSearch replication lambda
# (main.py). Mirrors the build.sh convention used by the other lambdas in
# this repo (see lambda/name-resolution-opensearch/build.sh).

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${ROOT_DIR}/package"
ZIP_FILE="${ROOT_DIR}/function.zip"

rm -rf "${BUILD_DIR}" "${ZIP_FILE}"
mkdir -p "${BUILD_DIR}"

python3 -m pip install -r "${ROOT_DIR}/requirements.txt" -t "${BUILD_DIR}"
cp "${ROOT_DIR}/main.py" "${BUILD_DIR}/"

cd "${BUILD_DIR}"
zip -r "${ZIP_FILE}" .
