ARG ARCH=armv7hf
ARG VERSION=12.2.0
ARG UBUNTU_VERSION=24.04
ARG SDK_REGISTRY=docker.io/axisecp
FROM ${SDK_REGISTRY}/acap-native-sdk:${VERSION}-${ARCH}-ubuntu${UBUNTU_VERSION}

WORKDIR /opt/app
COPY . .
RUN . /opt/axis/acapsdk/environment-setup* && acap-build .
