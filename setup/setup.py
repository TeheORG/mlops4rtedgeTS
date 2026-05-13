#!/usr/bin/env python3

import subprocess
import sys
import shutil
import importlib.util
from pathlib import Path
import argparse
import os

ROOT = Path(__file__).resolve().parents[1]
VENV = Path(os.environ.get("MLOPS_VENV_PATH", ROOT / ".venv"))
CONFIG_DIR = ROOT / ".mlops4ofp"
CONFIG_FILE = CONFIG_DIR / "setup.yaml"


def venv_python_path():
    return VENV / "Scripts" / "python.exe" if sys.platform == 'win32' else VENV / "bin" / "python"


def venv_pip_path():
    return VENV / "Scripts" / "pip.exe" if sys.platform == 'win32' else VENV / "bin" / "pip"


# ============================================================
# UTILIDADES
# ============================================================

def abort(msg):
    print(f"\n[ERROR] {msg}")
    sys.exit(1)


def run(cmd, cwd=ROOT):
    print("[CMD]", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def find_python_311():
    candidates = [
        "python3.11",
        "python",
        "/usr/local/bin/python3.11",
        "/opt/homebrew/bin/python3.11",
    ]
    
    # En Windows, agregar más candidatos comunes
    if sys.platform == 'win32':
        candidates = [
            "python",
            "py",  # Launcher de Python en Windows
            "python3",
            r"C:\Python311\python.exe",
            r"C:\ProgramData\chocolatey\bin\python3.11.EXE",
        ] + candidates
    
    for c in candidates:
        path = shutil.which(c) 
        if path:
            return path
    print("[ERROR] No se encontró python3.11 en el sistema.")
    return None


# ============================================================
# VENV
# ============================================================

def ensure_venv():

    if VENV.exists():
        return

    python311 = find_python_311()
    if not python311:
        abort(
            "No se encontró python3.11.\n"
            "Instálalo antes de continuar."
        )

    print(f"[INFO] Usando Python 3.11: {python311}")
    
    # En Windows, usar manejo más robusto debido a problemas con subprocess.run
    if sys.platform == 'win32':
        venv_cmd = [python311, "-m", "venv", str(VENV)]
        print("[CMD]", " ".join(venv_cmd))
        result = subprocess.run(venv_cmd, cwd=ROOT, capture_output=True, text=True)
        if result.returncode != 0:
            print("[ERROR] Salida:")
            print(result.stdout)
            print(result.stderr)
            abort(f"Falló creación del venv (código {result.returncode})")
    else:
        # macOS/Linux: usar el método original que ya funciona
        run([python311, "-m", "venv", str(VENV)])

    pip = venv_pip_path()
    python = venv_python_path()


    try:
        run([str(pip), "install", "--upgrade", "pip"])
    except subprocess.CalledProcessError:
        print("[INFO] Pip ya está actualizado o no es necesario actualizar.")


    req = ROOT / "requirements.txt"
    if not req.exists():
        abort("requirements.txt no encontrado")

    run([str(pip), "install", "-r", str(req)])

    print("[INFO] Verificando TensorFlow...")
    subprocess.run(
        [str(python), "-c", "import tensorflow as tf; print(tf.__version__)"],
        check=True,
    )

    print("[OK] Entorno virtual creado correctamente")


def ensure_running_in_venv(config_path):

    venv_python = venv_python_path()

     # Verifica si el script está siendo ejecutado dentro del entorno virtual
    if Path(sys.executable).resolve() != venv_python.resolve():
        print("[INFO] Reejecutando dentro de .venv")
        try:
            subprocess.run([str(venv_python), __file__, "--config", config_path], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] El comando falló con el siguiente error: {e}")
            sys.exit(1)
        sys.exit(0)

# Deberian estar todas las librerias en requirements.txt, pero por si acaso garantizamos estas que son críticas para el pipeline TEHE-E
def ensure_runtime_tools_in_venv():
    """Garantiza herramientas Python obligatorias del pipeline en .venv."""
    pip = venv_pip_path()
    venv_python = venv_python_path()

    required_modules = {
        "serial": "pyserial>=3.5",
        "esptool": "esptool>=4.7",
    }

    def module_available(module_name):
        result = subprocess.run(
            [str(venv_python), "-c", f"import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('{module_name}') else 1)"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    missing_packages = [
        package for module, package in required_modules.items()
        if not module_available(module)
    ]

    if missing_packages:
        print(f"[INFO] Instalando dependencias runtime faltantes: {', '.join(missing_packages)}")
        run([str(pip), "install", *missing_packages])

    unresolved = [
        module for module in required_modules
        if not module_available(module)
    ]
    if unresolved:
        abort(
            "No se pudieron resolver dependencias runtime obligatorias en .venv: "
            + ", ".join(unresolved)
        )

    print("[OK] Dependencias runtime obligatorias presentes (pyserial, esptool)")


# ============================================================
# GIT
# ============================================================

def setup_git(cfg):

    git_cfg = cfg.get("git", {})
    mode = git_cfg.get("mode", "none")
    remote_url = git_cfg.get("remote_url")
    publish_remote_name = git_cfg.get("publish_remote_name", "publish")
    branch = git_cfg.get("branch", "main")

    # Si no existe repo → crear
    if not (ROOT / ".git").exists():
        print("[INFO] Inicializando repositorio Git")
        run(["git", "init"])

    if mode == "none":
        return

    if mode == "custom":

        if not remote_url:
            abort("git.remote_url obligatorio en modo custom")

        existing = subprocess.run(
            ["git", "remote", "get-url", publish_remote_name],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

        if existing.returncode == 0:
            print(f"[INFO] Actualizando remote '{publish_remote_name}'")
            run(["git", "remote", "set-url", publish_remote_name, remote_url])
        else:
            print(f"[INFO] Añadiendo remote '{publish_remote_name}'")
            run(["git", "remote", "add", publish_remote_name, remote_url])


# ============================================================
# DVC
# ============================================================

def add_or_update_dvc_remote(venv_python, name, url):

    result = subprocess.run(
        [str(venv_python), "-m", "dvc", "remote", "add", "-d", name, url],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("[INFO] Remote DVC ya existe → actualizando URL")
        run([
            str(venv_python), "-m", "dvc",
            "remote", "modify", name, "url", url
        ])


def setup_dvc(cfg):

    venv_python = venv_python_path()

    if not (ROOT / ".dvc").exists():
        print("[INFO] Inicializando DVC")
        run([str(venv_python), "-m", "dvc", "init"])

    dvc_cfg = cfg.get("dvc", {})
    backend = dvc_cfg.get("backend")

    if backend is None:
        print("[INFO] No se especifica backend DVC, omitiendo configuración de remoto")
        return

    elif backend == "local":

        path = ROOT / dvc_cfg.get("path", ".dvc_storage")
        path.mkdir(parents=True, exist_ok=True)

        add_or_update_dvc_remote(venv_python, "storage", str(path))

    elif backend == "dagshub":

        # repo = dvc_cfg.get("repo")
        repo_url = dvc_cfg.get("url")
        if not repo_url:
            abort("dvc.repo obligatorio para backend dagshub")

        user = os.environ.get("DAGSHUB_USER")
        token = os.environ.get("DAGSHUB_TOKEN")

        if not user or not token:
            abort(
                "Faltan variables de entorno:\n"
                "export DAGSHUB_USER=...\n"
                "export DAGSHUB_TOKEN=..."
            )

        # remote_url = f"https://dagshub.com/{repo}.dvc"

        add_or_update_dvc_remote(venv_python, "storage", repo_url)

        run([str(venv_python), "-m", "dvc", "remote", "modify", "storage", "--local", "auth", "basic"])
        run([str(venv_python), "-m", "dvc", "remote", "modify", "storage", "--local", "user", user])
        run([str(venv_python), "-m", "dvc", "remote", "modify", "storage", "--local", "password", token])

    else:
        abort(f"Backend DVC no soportado: {backend}")


# ============================================================
# MLFLOW
# ============================================================

def setup_mlflow(cfg):

    ml = cfg.get("mlflow", {})

    if not ml.get("enabled", False):
        return

    backend = ml.get("backend")

    if backend is None:
        abort("mlflow.backend obligatorio si mlflow.enabled=true")
        return
    
    elif backend == "local":
        tracking_uri = ml.get("tracking_uri")
        if not tracking_uri:
            abort("mlflow.tracking_uri obligatorio si enabled=true")

        CONFIG_DIR.mkdir(exist_ok=True)

        env_file = CONFIG_DIR / "env.sh"

        content = [
            "#!/usr/bin/env sh",
            "# Generado automáticamente por setup.py",
            f"export MLFLOW_TRACKING_URI={tracking_uri}",
        ]

        env_file.write_text("\n".join(content))
        env_file.chmod(0o755)
    elif backend == "dagshub":
        tracking_uri = ml.get("tracking_uri")
        if not tracking_uri:
            abort("mlflow.url obligatorio para backend dagshub")

        # Para DAGsHub, el tracking URI se configura también en env.sh para que esté disponible en runtime
        CONFIG_DIR.mkdir(exist_ok=True)
        env_file = CONFIG_DIR / "env.sh"

        content = [
            "#!/usr/bin/env sh",
            "# Generado automáticamente por setup.py",
            f"export MLFLOW_TRACKING_URI={tracking_uri}",
        ]

        env_file.write_text("\n".join(content))
        env_file.chmod(0o755)
    else:
        abort(f"Backend MLflow no soportado: {backend}")


def ensure_minimal_executions_structure():
    base_src = ROOT / "setup" / "executions"
    base_dst = ROOT / "executions"

    base_dst.mkdir(exist_ok=True)

    if not base_src.exists():
        print("[WARN] No existe setup/executions — no se copian base_params")
        return

    for phase_dir in base_src.iterdir():
        if not phase_dir.is_dir():
            continue

        dst_phase = base_dst / phase_dir.name
        dst_phase.mkdir(exist_ok=True)

        for f in phase_dir.iterdir():
            dst_file = dst_phase / f.name
            if not dst_file.exists():
                shutil.copy(f, dst_file)
                print(f"[INFO] Copiado base estático: {dst_file}")


from datetime import datetime
import subprocess
import yaml

def write_pipeline_ref():
    CONFIG_DIR.mkdir(exist_ok=True)
    ref_path = CONFIG_DIR / "pipeline_ref.yaml"

    # Intentar obtener commit actual si existe repo git
    commit = "unknown"
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True
        ).strip()
    except Exception:
        pass

    ref = {
        "mode": "development",  # importante
        "pipeline_git_commit": commit,
        "created_at": datetime.utcnow().isoformat() + "Z"
    }

    ref_path.write_text(yaml.safe_dump(ref, sort_keys=False))
    print(f"[INFO] pipeline_ref.yaml creado ({ref['mode']})")
    
# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    print("====================================")
    print(" MLOps4OFP — Setup definitivo")
    print("====================================")

    ensure_venv()
    ensure_running_in_venv(args.config)
    ensure_runtime_tools_in_venv()

    import yaml

    if CONFIG_FILE.exists():
        abort(
            "El proyecto ya tiene un setup previo.\n"
            "Ejecuta primero: make clean-setup\n"
            "y después vuelve a lanzar make setup."
        )

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        abort(f"No existe {cfg_path}")

    cfg = yaml.safe_load(cfg_path.read_text())

    setup_git(cfg)
    setup_dvc(cfg)
    setup_mlflow(cfg)

    CONFIG_DIR.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(yaml.dump(cfg))
    ensure_minimal_executions_structure()

    write_pipeline_ref()
    print("\n[OK] Setup completado correctamente")
    print("Ejecuta ahora: make check-setup")


if __name__ == "__main__":
    main()
