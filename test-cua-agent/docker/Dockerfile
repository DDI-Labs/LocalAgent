# Extend CUA's base XFCE image with NoMachine client
FROM trycua/cua-xfce:latest

USER root

# Install dependencies for NoMachine
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    xdg-utils \
    libcap2 \
    libglib2.0-0 \
    libegl1 \
    && rm -rf /var/lib/apt/lists/*

# Download and install NoMachine client (free edition)
# Update the version/URL as needed: https://downloads.nomachine.com/linux/
ARG NOMACHINE_VERSION=8.20.1_1
ARG NOMACHINE_PKG=nomachine_${NOMACHINE_VERSION}_amd64.deb
RUN curl -fSL "https://download.nomachine.com/download/8.20/Linux/${NOMACHINE_PKG}" -o /tmp/${NOMACHINE_PKG} \
    && dpkg -i /tmp/${NOMACHINE_PKG} || apt-get install -f -y \
    && rm /tmp/${NOMACHINE_PKG}

# Don't switch user — supervisord needs root
