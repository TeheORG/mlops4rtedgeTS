# 1. Definir la variable (usamos $HOME en lugar de ~ por seguridad en scripts)
VIRTUAL_ENV="$HOME/.venv"

# 2. Crear el entorno virtual
python3 -m venv "$VIRTUAL_ENV"

# 3. Hacerlo PERMANENTE para el usuario runner en futuros inicios de sesión
echo "export VIRTUAL_ENV=\"$VIRTUAL_ENV\"" >> ~/.bashrc
echo 'export PATH="$VIRTUAL_ENV/bin:$PATH"' >> ~/.bashrc

# 4. Aplicarlo INMEDIATAMENTE en esta terminal actual
export VIRTUAL_ENV="$VIRTUAL_ENV"
export PATH="$VIRTUAL_ENV/bin:$PATH"

# 5. Instalar dependencias (pip ahora es mágicamente el pip del venv)
pip install --upgrade pip setuptools wheel
# pip install -r /tmp/requirements.txt # (Descomenta esto si el archivo realmente está en /tmp)