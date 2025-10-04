VENDOR=Elektrobit
NAME=Blob
IMAGE_FORMAT=tgz
IMAGE_GLOB=*.tgz
VERSION=$(shell echo $(IMAGE) | sed -e 's/.*-\([-0-9a-zA-A]\{1,\}\)\.tgz/\1/')


-include ../makefile-sanity.include
-include ../makefile.include
-include ../makefile-install.include

docker-build-image-copy:
	./extract.sh $(IMAGE)
