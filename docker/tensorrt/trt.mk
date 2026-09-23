BOARDS += trt

# Tag applied to the TensorRT images. Defaults to the CI scheme
# (<branch>-<commit>); override it to publish under a friendlier name, e.g.
#   make push-trt IMAGE_REPO=docker.io/you/frigate TRT_TAG=0.19.0
# The -jp5 / -jp6 suffixes are appended to this for the Jetson variants.
TRT_TAG ?= ${GITHUB_REF_NAME}-$(COMMIT_HASH)

JETPACK5_BASE ?= nvcr.io/nvidia/l4t-tensorrt:r8.5.2-runtime	# L4T 35.3.1 JetPack 5.1.1
JETPACK6_BASE ?= nvcr.io/nvidia/tensorrt:23.12-py3-igpu
# COMPUTE_LEVEL only reaches tensorrt_libyolo.sh, which builds the tensorrt_demos
# YOLO plugins, and only Dockerfile.arm64 consumes it. The amd64 image ignores
# it: the ONNX Runtime TensorRT EP compiles engines at runtime for whichever GPU
# is present, so narrowing this list does not speed up or change the x86 build.
X86_DGPU_ARGS := ARCH=amd64 COMPUTE_LEVEL="50 60 70 80 90"
JETPACK5_ARGS := ARCH=arm64 BASE_IMAGE=$(JETPACK5_BASE) SLIM_BASE=$(JETPACK5_BASE) TRT_BASE=$(JETPACK5_BASE)
JETPACK6_ARGS := ARCH=arm64 BASE_IMAGE=$(JETPACK6_BASE) SLIM_BASE=$(JETPACK6_BASE) TRT_BASE=$(JETPACK6_BASE)

local-trt: version
	$(X86_DGPU_ARGS) docker buildx bake --file=docker/tensorrt/trt.hcl tensorrt \
		--set tensorrt.tags=frigate:latest-tensorrt \
		--load

local-trt-jp5: version
	$(JETPACK5_ARGS) docker buildx bake --file=docker/tensorrt/trt.hcl tensorrt \
		--set tensorrt.tags=frigate:latest-tensorrt-jp5 \
		--load

local-trt-jp6: version
	$(JETPACK6_ARGS) docker buildx bake --file=docker/tensorrt/trt.hcl tensorrt \
		--set tensorrt.tags=frigate:latest-tensorrt-jp6 \
		--load

build-trt:
	$(X86_DGPU_ARGS) docker buildx bake --file=docker/tensorrt/trt.hcl tensorrt \
		--set tensorrt.tags=$(IMAGE_REPO):$(TRT_TAG)-tensorrt
	$(JETPACK5_ARGS) docker buildx bake --file=docker/tensorrt/trt.hcl tensorrt \
		--set tensorrt.tags=$(IMAGE_REPO):$(TRT_TAG)-tensorrt-jp5
	$(JETPACK6_ARGS) docker buildx bake --file=docker/tensorrt/trt.hcl tensorrt \
		--set tensorrt.tags=$(IMAGE_REPO):$(TRT_TAG)-tensorrt-jp6

push-trt: build-trt
	$(X86_DGPU_ARGS) docker buildx bake --file=docker/tensorrt/trt.hcl tensorrt \
		--set tensorrt.tags=$(IMAGE_REPO):$(TRT_TAG)-tensorrt \
		--push
	$(JETPACK5_ARGS) docker buildx bake --file=docker/tensorrt/trt.hcl tensorrt \
		--set tensorrt.tags=$(IMAGE_REPO):$(TRT_TAG)-tensorrt-jp5 \
		--push
	$(JETPACK6_ARGS) docker buildx bake --file=docker/tensorrt/trt.hcl tensorrt \
		--set tensorrt.tags=$(IMAGE_REPO):$(TRT_TAG)-tensorrt-jp6 \
		--push
