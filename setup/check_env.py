#!/usr/bin/env python3
import subprocess
import sys
import shutil

REQUIRED_PYTHON = (3, 11)


def run(cmd):
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return True, out.decode().strip()
    except Exception as e:
        return False, str(e)

def check_python():
    v = sys.version_info
    if (v.major, v.minor) != REQUIRED_PYTHON:
        print(
            f"[ERROR] Python {v.major}.{v.minor}.{v.micro} no soportado\n"
            "   Se requiere exactamente Python 3.11.x para todo el entorno host del proyecto\n"
            "   (scripts ML/F07 + esptool). ESP-IDF/tflite-micro se ejecuta en Docker."
        )
        return False

    print(f"[OK] Python {v.major}.{v.minor}.{v.micro}")
    return True

def check_python_module(module_name, mandatory=True):
    try:
        __import__(module_name)
        print(f"[OK] Python module '{module_name}'")
        return True
    except ImportError:
        if mandatory:
            print(f"[ERROR] Python module '{module_name}' no instalado")
            return False
        else:
            print(f"[WARN] Python module '{module_name}' no instalado (opcional)")
            return True

def check_tool(name, mandatory=True):
    if shutil.which(name) is None:
        if mandatory:
            print(f"[ERROR] {name} no encontrado en PATH")
            return False
        else:
            print(f"[WARN] {name} no encontrado (opcional)")
            return True

    ok, out = run([name, "--version"])
    if ok:
        print(f"[OK] {name}: {out}")
    else:
        print(f"[WARN] {name} encontrado pero no responde correctamente")
    return True

def check_tensorflow():
    try:
        import tensorflow as tf
        v = tuple(map(int, tf.__version__.split(".")[:2]))
        if not (v[0] == 2 and v[1] == 15):
            print(f"[ERROR] TensorFlow {tf.__version__} no soportado (usar 2.15.x)")
            return False
        print(f"[OK] TensorFlow {tf.__version__}")
        return True
    except Exception as e:
        print(f"[ERROR] TensorFlow no funciona: {e}")
        return False



def main():
    print("===================================")
    print(" CHECK ENTORNO — MLOps4OFP")
    print("===================================")

    ok = True

    ok &= check_python()
    ok &= check_tool("git", mandatory=True)
    check_tool("dvc", mandatory=False)

    ok &= check_python_module("mlflow", mandatory=True)
    ok &= check_tool("mlflow", mandatory=False)
    ok &= check_tensorflow()

    if not ok:
        print("\n[ERROR] Entorno NO válido para continuar con el setup")
        sys.exit(1)

    print("\n[OK] Entorno básico correcto")

if __name__ == "__main__":
    main()
