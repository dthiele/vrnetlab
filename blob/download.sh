#!/bin/bash
set -euo pipefail

FS_URL="file://$(find /home/dath1233/repositories/linux/build/tmp/deploy/images/ -name evos-image-zcu-qemuarm64-evos-zcu-*.rootfs.ext4 | tail -1)"
KERNEL_URL="file://$(find /home/dath1233/repositories/linux/build/tmp/deploy/images/ -name Image | tail -1)"

STAGE_DIR=$(mktemp -d)
curl --output-dir "${STAGE_DIR}" --output $(basename "${FS_URL}") "${FS_URL}"
curl --output-dir "${STAGE_DIR}" --output $(basename "${KERNEL_URL}") "${KERNEL_URL}"
tar -C "${STAGE_DIR}" -czf $(basename "${FS_URL}" | sed -e 's/\.rootfs.ext4$/.tgz/') .
rm -rf "${STAGE_DIR}"
