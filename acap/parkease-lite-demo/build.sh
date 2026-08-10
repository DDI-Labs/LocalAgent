#!/bin/sh
# Builds the ParkEase LITE demo ACAP for armv7hf and copies the .eap
# into ./out/. Requires Docker.
set -e
cd "$(dirname "$0")"

ARCH="${1:-armv7hf}"
IMAGE="parkease-lite-demo:$ARCH"

# SDK_REGISTRY can point at a Docker Hub mirror if docker.io is unreachable,
# e.g. SDK_REGISTRY=mirror.gcr.io/axisecp ./build.sh
SDK_REGISTRY="${SDK_REGISTRY:-docker.io/axisecp}"

docker build --build-arg "ARCH=$ARCH" --build-arg "SDK_REGISTRY=$SDK_REGISTRY" -t "$IMAGE" .

mkdir -p out
CID="$(docker create "$IMAGE")"
docker cp "$CID:/opt/app/." out/tmp-export
docker rm "$CID" > /dev/null
mv out/tmp-export/*.eap out/ 2>/dev/null || true
rm -rf out/tmp-export

ls -l out/*.eap
echo "Done. Upload the .eap via the camera's Apps page (enable unsigned apps first)."
