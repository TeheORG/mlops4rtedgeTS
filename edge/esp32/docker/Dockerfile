# ============================================================
# MLOps4OFP — ESP32 Runtime Docker (IDF 6.0)
# ============================================================

FROM espressif/idf:release-v6.0

# Directorio de trabajo dentro del contenedor
WORKDIR /project

# Opcional: herramientas útiles para debug/log parsing
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*
