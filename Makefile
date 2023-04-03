################################################################################
# Variables                                                                    #
################################################################################

BUILD_PATH ?= ./postgres-appliance
DOCKERFILE_PATH ?= ./postgres-appliance/Dockerfile
DOCKER_BUILD_ARGS = --build-arg PGVERSION="15"
BUILDX_PLATFORMS ?= linux/amd64,linux/arm64
VERSION ?= latest
IMG ?= docker.io/apecloud/spilo
BUILDX_ARGS ?=

.PHONY: push-image
push-image:
	cd postgres-appliance
	docker buildx build $(BUILD_PATH) -f $(DOCKERFILE_PATH) $(DOCKER_BUILD_ARGS) --platform $(BUILDX_PLATFORMS) -t $(IMG):$(VERSION) --push $(BUILDX_ARGS)
