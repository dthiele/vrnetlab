#!/bin/bash
set -euo pipefail


echo "Prepating file system and kernel"
rm -rf docker/images
mkdir -p docker/images

filepath="$(find /home/dath1233/repositories/linux/build/tmp/deploy/images/ -name evos-image-zcu-qemuarm64-evos-zcu-*.rootfs.ext4 | tail -1)"
filename="$(basename ${filepath})"
kernelpath="$(find /home/dath1233/repositories/linux/build/tmp/deploy/images/ -name Image | tail -1)"
kernelname=$(basename ${kernelpath})

# Check if the file already exists in the current directory
if [ -e "docker/images/${filename}" ]; then
    echo "File ${filename} already exists. Skipping download."
else
    cp "${filepath}" "docker/images/${filename}"
    echo "Download complete: ${filename}"
fi
if [ -e "docker/images/${kernelname}" ]; then
    echo "File ${kernelname} already exists. Skipping download."
else
    cp "${kernelpath}" "docker/images/${kernelname}"
    echo "Download complete: ${kernelname}"
fi
