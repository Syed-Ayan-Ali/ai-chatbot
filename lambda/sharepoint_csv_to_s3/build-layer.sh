#!/usr/bin/env bash
# Build a Lambda layer zip with the correct python/ layout for Amazon Linux.
# Run from any machine that has Docker installed.
#
# Usage:
#   ./build-layer.sh 3.12
#
# Output: dist/office365-library.zip

set -euo pipefail

PYTHON_VERSION="${1:-3.12}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${SCRIPT_DIR}/dist"
LAYER_DIR="${OUT_DIR}/layer"
ZIP_PATH="${OUT_DIR}/office365-library.zip"

rm -rf "${LAYER_DIR}" "${ZIP_PATH}"
mkdir -p "${LAYER_DIR}/python"

echo "Installing dependencies for Python ${PYTHON_VERSION} (Amazon Linux)..."

docker run --rm \
  -v "${SCRIPT_DIR}:/src" \
  -v "${LAYER_DIR}/python:/out" \
  "public.ecr.aws/lambda/python:${PYTHON_VERSION}" \
  bash -c "pip install -r /src/requirements.txt -t /out --no-cache-dir"

echo "Creating layer zip..."
(
  cd "${LAYER_DIR}"
  zip -r9 "${ZIP_PATH}" python
)

echo "Done: ${ZIP_PATH}"
echo ""
echo "Upload this zip as a Lambda layer. Expected structure inside the zip:"
echo "  python/msal/"
echo "  python/office365/"
echo "  python/boto3/"
