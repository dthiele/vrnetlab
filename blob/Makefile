VENDOR=Elektrobit
NAME=Blob
IMAGE_FORMAT=ext4
IMAGE_GLOB=*.ext4

VERSION=$(shell echo $(IMAGE) | sed -e 's/.*-\([-0-9a-zA-A]\{1,\}\)\.rootfs.*/\1/')


-include ../makefile-sanity.include
-include ../makefile.include
-include ../makefile-install.include

docker-build-image-copy:
	/bin/bash download.sh
