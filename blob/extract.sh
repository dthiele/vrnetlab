#!/bin/bash
set -euo pipefail

IMAGE=$1

echo "Extracting ${1}"
rm -rf docker/images
mkdir -p docker/images
tar -xzvf "${IMAGE}" -C docker/images
