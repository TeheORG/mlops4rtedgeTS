FROM espressif/idf:release-v6.0

ARG TARGETARCH
ARG QEMU_INSTALL_DIR=/opt/qemu-esp32

ENV DEBIAN_FRONTEND=noninteractive
ENV F07_IDF_RUNNER=native
ENV PYTHONUNBUFFERED=1

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    cmake \
    curl \
    git \
    make \
    ninja-build \
    pkg-config \
    procps \
    python3 \
    python3-pip \
    python3-venv \
    socat \
    xz-utils \
    build-essential \
    libglib2.0-dev \
    libpixman-1-dev \
    libslirp-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/esp32-virt-venv \
    && /opt/esp32-virt-venv/bin/python -m pip install --upgrade --no-cache-dir pip \
    && /opt/esp32-virt-venv/bin/python -m pip install --no-cache-dir \
    "esptool>=4.7" \
    "flatbuffers>=2.0" \
    matplotlib \
    numpy \
    pandas \
    pyarrow \
    pyserial \
    pyyaml

RUN /opt/esp32-virt-venv/bin/python -c "import pandas, pyarrow, serial, yaml"

RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
      amd64) qemu_arch="x86_64" ;; \
      arm64) qemu_arch="aarch64" ;; \
      *) echo "Unsupported Docker TARGETARCH=${TARGETARCH:-unknown}"; exit 1 ;; \
    esac; \
    asset_url="$(curl -fsSL --max-time 30 https://api.github.com/repos/espressif/qemu/releases/latest \
      | grep browser_download_url \
      | grep xtensa \
      | grep "${qemu_arch}-linux-gnu" \
      | grep '\.tar\.xz' \
      | head -1 \
      | cut -d '"' -f 4)"; \
    if [ -n "$asset_url" ]; then \
      tmpfile="$(mktemp /tmp/qemu-esp32-XXXXXX.tar.xz)"; \
      curl -fL --max-time 240 "$asset_url" -o "$tmpfile"; \
      mkdir -p "${QEMU_INSTALL_DIR}"; \
      tar -xJf "$tmpfile" -C "${QEMU_INSTALL_DIR}" --strip-components=1; \
      rm -f "$tmpfile"; \
    else \
      tmpdir="$(mktemp -d /tmp/qemu-esp32-src-XXXXXX)"; \
      git clone --depth=1 https://github.com/espressif/qemu.git "$tmpdir"; \
      cd "$tmpdir"; \
      ./configure \
        --target-list=xtensa-softmmu \
        --prefix="${QEMU_INSTALL_DIR}" \
        --disable-werror \
        --disable-docs; \
      ninja -C build; \
      ninja -C build install; \
      rm -rf "$tmpdir"; \
    fi; \
    "${QEMU_INSTALL_DIR}/bin/qemu-system-xtensa" --version

ENV PATH="/opt/esp32-virt-venv/bin:/opt/qemu-esp32/bin:${PATH}"

CMD ["bash"]
