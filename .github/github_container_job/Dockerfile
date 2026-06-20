# GitHub Container Registry (GHCR)
# Imagen ligera de Python 3.11 para MLOps
FROM python:3.11-slim

# Configuración de Python para mejor rendimiento
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 1️⃣ LA CLAVE ESTÁ AQUÍ: Añadimos el venv al PATH del sistema
ENV VIRTUAL_ENV=/opt/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Instala herramientas del sistema + crea venv (el venv se crea en la ruta de arriba)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    make \
    procps \
    util-linux \
    curl \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | gpg --dearmor -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/* \
    && python3.11 -m venv $VIRTUAL_ENV

COPY requirements.txt /tmp/

# Instala dependencias. 
# Como ya está en el PATH, podemos usar 'pip' directamente en lugar de '/opt/.venv/bin/pip'
RUN pip install --upgrade pip "setuptools>=68,<81" wheel && \
    pip install -r /tmp/requirements.txt 

# Instala dependencias y limpia cachés de forma segura
RUN find $VIRTUAL_ENV -type f -name "*.pyc" -delete && \
    find $VIRTUAL_ENV -type d -name "__pycache__" -exec rm -rf {} + && \
    find $VIRTUAL_ENV -type d -name "tests" -exec rm -rf {} + && \
    rm -rf /tmp/requirements.txt /root/.cache/pip

WORKDIR /workspace

CMD ["/bin/bash"]