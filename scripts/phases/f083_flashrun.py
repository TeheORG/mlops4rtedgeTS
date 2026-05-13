#!/usr/bin/env python3
"""
F08 — SYSTEM VALIDATION (MULTI-MODEL EDGE) — FLASH & RUN

Flujo nativo para ESP32 y flujo basado en runners para otras plataformas.
Además exporta artefactos de build reproducibles al directorio de variante.
"""

import argparse
import subprocess
import time
import sys
import shutil
import os
import shlex
from pathlib import Path

import serial
from serial.tools import list_ports
import yaml

from scripts.core.artifacts import PROJECT_ROOT, get_variant_dir

PHASE = "f08_sysval"
IDF_DOCKER_IMAGE = "mlops4ofp-idf:6.0"


# ============================================================
# UTILIDADES
# ============================================================

def run_and_log(
    cmd,
    log_path: Path,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    echo_output: bool = False,
):
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(log_path, "w") as log:
        process = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )

        try:
            for line in process.stdout:
                if echo_output:
                    print(line, end="")
                log.write(line)

            process.wait()
        except KeyboardInterrupt:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            raise

        if process.returncode in (130, -2):
            raise KeyboardInterrupt

        if process.returncode != 0:
            raise RuntimeError(
                f"[F08] Command failed ({process.returncode}): {' '.join(cmd)}"
            )


def run_and_log_result(
    cmd,
    log_path: Path,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    echo_output: bool = False,
) -> tuple[int, str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    with open(log_path, "a") as log:
        process = subprocess.Popen(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )

        try:
            for line in process.stdout:
                if echo_output:
                    print(line, end="")
                log.write(line)
                lines.append(line)

            process.wait()
        except KeyboardInterrupt:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            raise

    return process.returncode, "".join(lines)


def get_host_user_spec() -> str:
    """Devuelve UID:GID del proceso host para ejecutar Docker sin root."""
    return f"{os.getuid()}:{os.getgid()}"


def get_serial_device_gid(port: str | None) -> str | None:
    """Devuelve el GID del dispositivo serie para group-add en Docker."""
    if not port:
        return None
    try:
        return str(os.stat(port).st_gid)
    except OSError:
        return None


def build_idf_command(
    idf_args: list[str],
    esp_project_dir: Path,
    port: str | None = None,
    cmake_parallel_level: str | None = None,
    docker_memory_limit: str | None = None,
    docker_memory_swap: str | None = None,
    docker_cpus: str | None = None,
) -> list[str]:
    quoted_args = " ".join(shlex.quote(arg) for arg in idf_args)
    parallel_prefix = ""
    if cmake_parallel_level is not None:
        level = shlex.quote(str(cmake_parallel_level))
        parallel_prefix = f"export CMAKE_BUILD_PARALLEL_LEVEL={level} && "

    shell_cmd = (
        "source /opt/esp/idf/export.sh >/dev/null 2>&1 && "
        f"{parallel_prefix}idf.py {quoted_args}"
    )

    cmd = [
        "docker", "run", "--rm", "-i",
        "--user", get_host_user_spec(),
        "-v", f"{esp_project_dir.resolve()}:/project",
        "-w", "/project",
        "--entrypoint", "/bin/bash",
    ]

    if docker_memory_limit:
        cmd.extend(["--memory", str(docker_memory_limit)])

    if docker_memory_swap:
        cmd.extend(["--memory-swap", str(docker_memory_swap)])

    if docker_cpus:
        cmd.extend(["--cpus", str(docker_cpus)])

    if port:
        cmd.extend(["--device", f"{port}:{port}"])
        serial_gid = get_serial_device_gid(port)
        if serial_gid:
            cmd.extend(["--group-add", serial_gid])

    cmd.extend([IDF_DOCKER_IMAGE, "-lc", shell_cmd])
    return cmd


def run_idf_and_log(
    idf_args: list[str],
    log_path: Path,
    esp_project_dir: Path,
    port: str | None = None,
    cmake_parallel_level: str | None = None,
    docker_memory_limit: str | None = None,
    docker_memory_swap: str | None = None,
    docker_cpus: str | None = None,
):
    cmd = build_idf_command(
        idf_args,
        esp_project_dir=esp_project_dir,
        port=port,
        cmake_parallel_level=cmake_parallel_level,
        docker_memory_limit=docker_memory_limit,
        docker_memory_swap=docker_memory_swap,
        docker_cpus=docker_cpus,
    )
    run_and_log(cmd, log_path, cwd=None)


def can_map_docker_device(port: str, image_name: str) -> tuple[bool, str]:
    serial_gid = get_serial_device_gid(port)
    probe = subprocess.run(
        [
            "docker", "run", "--rm",
            "--user", get_host_user_spec(),
            "--device", f"{port}:{port}",
            *(["--group-add", serial_gid] if serial_gid else []),
            "--entrypoint", "/bin/bash",
            image_name,
            "-lc", f"test -e {shlex.quote(port)}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if probe.returncode == 0:
        return True, ""

    stderr = (probe.stderr or "").strip()
    return False, stderr


def run_host_esptool_flash(port: str, esp_project_dir: Path, flash_log: Path) -> bool:
    build_dir = esp_project_dir / "build"
    flash_args = build_dir / "flash_args"
    if not flash_args.exists():
        return False

    print("[F08] Intentando flash en host con esptool")
    rc, _ = run_and_log_result(
        [
            sys.executable,
            "-m",
            "esptool",
            "--chip",
            "esp32",
            "-p",
            port,
            "-b",
            "460800",
            "--before",
            "default-reset",
            "--after",
            "hard-reset",
            "write-flash",
            "@flash_args",
        ],
        flash_log,
        cwd=build_dir,
        echo_output=False,
    )
    if rc == 0:
        return True

    raise RuntimeError("[F08] Falló el flash con esptool en host")


def flash_portable(
    port: str,
    flash_log: Path,
    esp_project_dir: Path,
    docker_memory_limit: str | None,
    docker_memory_swap: str | None,
    docker_cpus: str | None,
):
    if sys.platform == "darwin":
        print("[F08] Flash en host (macOS)")
        if run_host_esptool_flash(port, esp_project_dir, flash_log):
            return

    docker_ok, docker_err = can_map_docker_device(port, IDF_DOCKER_IMAGE)

    if docker_ok:
        print("[F08] Flash vía Docker")
        run_idf_and_log(
            ["-p", port, "flash"],
            flash_log,
            esp_project_dir=esp_project_dir,
            port=port,
            docker_memory_limit=docker_memory_limit,
            docker_memory_swap=docker_memory_swap,
            docker_cpus=docker_cpus,
        )
        return

    print("[F08] Docker no puede mapear el puerto serie; usando host")
    if docker_err:
        print(f"[F08] Detalle Docker: {docker_err}")

    if run_host_esptool_flash(port, esp_project_dir, flash_log):
        return

    raise RuntimeError(
        "[F08] No fue posible flashear de forma portable. "
        "No hay passthrough serie en Docker y falló el flash en host con esptool."
    )


def resolve_docker_memory_limit() -> str | None:
    env_value = os.environ.get("F08_DOCKER_MEMORY")
    if env_value:
        return env_value

    probe = subprocess.run(
        ["docker", "info", "--format", "{{.MemTotal}}"],
        capture_output=True,
        text=True,
        check=False,
    )

    if probe.returncode != 0:
        return None

    value = probe.stdout.strip()
    if value.isdigit() and int(value) > 0:
        return value

    return None


def resolve_docker_memory_swap() -> str | None:
    return os.environ.get("F08_DOCKER_MEMORY_SWAP")


def resolve_docker_cpus() -> str | None:
    return os.environ.get("F08_DOCKER_CPUS")


def sanitize_sdkconfig_for_docker(esp_project_dir: Path):
    sdkconfig_path = esp_project_dir / "sdkconfig"
    defaults_path = esp_project_dir / "sdkconfig.defaults"

    if not defaults_path.exists():
        return

    shutil.copy2(defaults_path, sdkconfig_path)
    print("[F08] sdkconfig regenerado desde sdkconfig.defaults para build Docker")


def sync_generated_sources_for_build(esp_project_dir: Path):
    src_dir = esp_project_dir / "build_generated"

    if not src_dir.exists():
        raise RuntimeError(
            "[F08] Falta build_generated. Ejecuta f082_preparebuild."
        )

    dst_dir = esp_project_dir / "build" / "build_generated"

    if dst_dir.exists():
        shutil.rmtree(dst_dir)

    shutil.copytree(src_dir, dst_dir)


# ============================================================
# EXPORT DE ARTEFACTOS DE BUILD
# ============================================================

def copy_if_exists(src: Path, dst: Path):
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True
    return False


def export_platform_build_artifacts(variant_dir: Path, project_dir: Path, platform: str):
    build_dir = project_dir / "build"
    if not build_dir.exists():
        return

    bundle_dir = variant_dir / "platform_build_bundle"
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    if platform == "esp32":
        candidates = [
            "bootloader/bootloader.bin",
            "partition_table/partition-table.bin",
            "flasher_args.json",
            "flash_args",
            "project_description.json",
        ]

        app_bin_candidates = list(build_dir.glob("*.bin"))
        for app_bin in app_bin_candidates:
            if app_bin.name not in {"bootloader.bin", "partition-table.bin"}:
                copy_if_exists(app_bin, bundle_dir / app_bin.name)

        for rel in candidates:
            src = build_dir / rel
            if src.exists():
                dst = bundle_dir / Path(rel).name
                copy_if_exists(src, dst)

        main_app = None
        for app_bin in app_bin_candidates:
            if app_bin.name not in {"bootloader.bin", "partition-table.bin"}:
                main_app = app_bin
                break

        if main_app:
            copy_if_exists(main_app, variant_dir / "application_image.bin")

        copy_if_exists(
            build_dir / "bootloader" / "bootloader.bin",
            variant_dir / "bootloader_image.bin",
        )
        copy_if_exists(
            build_dir / "partition_table" / "partition-table.bin",
            variant_dir / "partition_table_image.bin",
        )

    else:
        for item in build_dir.glob("*"):
            if item.is_file():
                copy_if_exists(item, bundle_dir / item.name)


# ============================================================
# AUTODETECCIÓN DE PUERTO
# ============================================================

def auto_detect_port():
    ports = list_ports.comports()

    def is_usb_candidate(p):
        dev = (p.device or "").lower()
        desc = (p.description or "").lower()
        manu = (p.manufacturer or "").lower()

        # Prioridad 1: puertos con VID/PID (puertos USB reales), excluye virtuales
        if (p.vid is not None) and (p.pid is not None):
            return True

        # Prioridad 2: texto que indica puerto serie/UART, pero excluye explícitamente virtuales macOS
        hints = ("usb", "uart", "cp210", "ch340", "wch", "silicon", "ftdi", "ttyusb", "ttyacm")
        by_text = any(h in dev or h in desc or h in manu for h in hints)

        # Excluye explícitamente puertos virtuales comunes en macOS
        virt_hints = ("bluetooth", "debug-console", "incoming-port")
        is_virtual = any(h in dev or h in desc for h in virt_hints)

        return by_text and not is_virtual

    if len(ports) == 0:
        return None
    if len(ports) == 1:
        return ports[0].device

    usb_ports = [p.device for p in ports if is_usb_candidate(p)]
    if len(usb_ports) == 1:
        return usb_ports[0]

    return "MULTIPLE"


def describe_serial_ports() -> str:
    ports = list_ports.comports()
    if not ports:
        return "(sin puertos detectados)"

    lines: list[str] = []
    for p in ports:
        description = p.description or "n/a"
        manufacturer = p.manufacturer or "n/a"
        hwid = p.hwid or "n/a"
        lines.append(
            f"- {p.device} | desc={description} | manufacturer={manufacturer} | hwid={hwid}"
        )

    return "\n".join(lines)



# ============================================================
# SERIAL / RUN
# ============================================================

def load_lines_for_serial(path: Path) -> list[str]:
    text = path.read_text()
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
    return lines


def resolve_max_mti_ms(edge_cfg: dict):
    models = edge_cfg.get("models")
    if isinstance(models, list) and models:
        values = []
        for model in models:
            if not isinstance(model, dict):
                continue
            v = model.get("mti_ms", model.get("MTI_MS"))
            if v is not None:
                values.append(float(v))
        if values:
            return max(values), None

    limits = edge_cfg.get("limits", {})
    mti_ms = limits.get("MTI_MS")
    legacy_mti = limits.get("MTI")
    return mti_ms, legacy_mti


def resolve_tu_ms(edge_cfg: dict):
    drain_cfg = edge_cfg.get("drain", {})
    if isinstance(drain_cfg, dict):
        tu_ms = drain_cfg.get("tu_ms")
        if tu_ms is not None:
            return float(tu_ms)

    geom = edge_cfg.get("geometry", {})
    if isinstance(geom, dict):
        tu_ms = geom.get("Tu_edge_ms")
        if tu_ms is not None:
            return float(tu_ms)

    return None


def resolve_project_dir(variant_dir: Path, edge_cfg: dict, platform: str) -> Path:
    execution = edge_cfg.get("execution", {})
    if isinstance(execution, dict):
        project_dir_name = execution.get("project_dir")
        if project_dir_name:
            project_dir = variant_dir / str(project_dir_name)
            if project_dir.exists():
                return project_dir

    platform_project = variant_dir / f"{platform}_project"
    if platform_project.exists():
        return platform_project

    legacy_esp = variant_dir / "esp32_project"
    if legacy_esp.exists():
        return legacy_esp

    raise RuntimeError(
        f"[F08] No se encuentra proyecto de plataforma para {platform}. "
        "Ejecuta f082_preparebuild."
    )


def resolve_runner_dir(variant_dir: Path, edge_cfg: dict, platform: str) -> Path:
    execution = edge_cfg.get("execution", {})
    if isinstance(execution, dict):
        runner_dir_name = execution.get("runner_dir")
        if runner_dir_name:
            runner_dir = variant_dir / str(runner_dir_name)
            if runner_dir.exists():
                return runner_dir

    fallback = variant_dir / f"{platform}_runner"
    if fallback.exists():
        return fallback

    raise RuntimeError(
        f"[F08] No se encuentra runner para platform={platform}. "
        f"Crea edge/{platform}/runner con build.sh, flash.sh y run.sh."
    )


def run_runner_script(
    script_path: Path,
    log_path: Path,
    env: dict[str, str],
    cwd: Path,
):
    if not script_path.exists():
        raise RuntimeError(f"[F08] Script runner no encontrado: {script_path}")

    run_and_log(["/bin/bash", str(script_path)], log_path, cwd=cwd, env=env)


def run_platform_runner_flow(
    platform: str,
    variant: str,
    variant_dir: Path,
    edge_cfg_path: Path,
    edge_cfg: dict,
    project_dir: Path,
    build_log: Path,
    flash_log: Path,
    monitor_log: Path,
    dataset_csv: Path,
    args,
):
    runner_dir = resolve_runner_dir(variant_dir, edge_cfg, platform)

    build_script = runner_dir / "build.sh"
    flash_script = runner_dir / "flash.sh"
    run_script = runner_dir / "run.sh"

    geom = edge_cfg.get("geometry", {})
    drain_cfg = edge_cfg.get("drain", {})
    tu_ms = resolve_tu_ms(edge_cfg)
    recommended = drain_cfg.get("recommended_drain_seconds") if isinstance(drain_cfg, dict) else None

    env = os.environ.copy()
    env.update(
        {
            "F08_PLATFORM": platform,
            "F08_VARIANT": variant,
            "F08_VARIANT_DIR": str(variant_dir.resolve()),
            "F08_PROJECT_DIR": str(project_dir.resolve()),
            "F08_EDGE_CONFIG": str(edge_cfg_path.resolve()),
            "F08_INPUT_DATASET": str(dataset_csv.resolve()),
            "F08_MODE": str(args.mode),
            "F08_BAUD": str(args.baud),
            "F08_TU_MS": str(tu_ms) if tu_ms is not None else "",
            "F08_RECOMMENDED_DRAIN_SECONDS": str(recommended) if recommended is not None else "",
            "F08_GEOM_OW": str(geom.get("OW", "")),
            "F08_GEOM_LT": str(geom.get("LT", "")),
            "F08_GEOM_PW": str(geom.get("PW", "")),
        }
    )

    if args.port:
        env["F08_PORT"] = str(args.port)

    if args.drain_seconds is not None:
        env["F08_DRAIN_SECONDS"] = str(args.drain_seconds)

    print(f"[F08] Ejecutando runner de plataforma: {platform}")
    print(f"[F08] Runner dir: {runner_dir}")

    run_runner_script(build_script, build_log, env=env, cwd=project_dir)

    if args.build_only:
        export_platform_build_artifacts(variant_dir, project_dir, platform)
        print("\n[F08] Build-only completado con éxito.")
        return

    run_runner_script(flash_script, flash_log, env=env, cwd=project_dir)
    run_runner_script(run_script, monitor_log, env=env, cwd=project_dir)

    export_platform_build_artifacts(variant_dir, project_dir, platform)

    print("\n[F08] Flash-run completado con éxito.")


def serial_send_and_monitor(
    port: str,
    baud: int,
    input_file: Path,
    log_path: Path,
    tunit_ms: float | None,
    post_wait_s: float,
):
    period = (tunit_ms or 1000.0) / 1000.0

    lines = load_lines_for_serial(input_file)
    if not lines:
        print("[F08-serial] No hay datos para enviar.")
        return

    print(f"[F08-serial] Puerto: {port}")
    print(f"[F08-serial] Baud: {baud}")
    print(f"[F08-serial] Periodo envío: {period:.3f}s")
    print(f"[F08-serial] Líneas a enviar: {len(lines)}")
    print(f"[F08-serial] Drenado final: {post_wait_s:.2f}s")
    print("[F08-serial] Progreso: '*' cada 100 líneas enviadas (10 '*' por línea)")

    ser = serial.Serial(port, baud, timeout=0)
    time.sleep(8.0)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    logf = open(log_path, "w")

    stopped_by_user = False
    progress_marks = 0

    def emit_progress(sent_lines: int):
        nonlocal progress_marks
        target_marks = (sent_lines + 99) // 100
        while progress_marks < target_marks:
            sys.stdout.write("*")
            progress_marks += 1
            if progress_marks % 10 == 0:
                sys.stdout.write("\n")
            sys.stdout.flush()

    try:
        next_send = time.monotonic()

        def drain_serial_once():
            pending = getattr(ser, "in_waiting", 0)
            if pending and pending > 0:
                data = ser.read(pending)
                if data:
                    text = data.decode("utf-8", errors="ignore")
                    logf.write(text)
                    logf.flush()

        for index, line in enumerate(lines, start=1):
            ser.write((line + "\n").encode("utf-8"))
            ser.flush()
            emit_progress(index)

            next_send += period

            while True:
                now = time.monotonic()
                remaining = next_send - now
                if remaining <= 0:
                    break
                drain_serial_once()
                time.sleep(min(0.01, max(0.0, remaining)))

        end_time = time.monotonic() + post_wait_s
        while time.monotonic() < end_time:
            drain_serial_once()
            time.sleep(0.05)

    except KeyboardInterrupt:
        stopped_by_user = True
        print("\n[F08-serial] Captura interrumpida por usuario (Ctrl+C). Continuando flujo.")

    finally:
        logf.close()
        ser.close()

    if progress_marks % 10 != 0:
        print("")

    if stopped_by_user:
        print("[F08-serial] Finalizado por usuario.")
    else:
        print("\n[F08-serial] Finalizado correctamente.")


def serial_monitor_only(
    port: str,
    baud: int,
    log_path: Path,
    post_wait_s: float,
):
    print(f"[F08-monitor] Puerto: {port}")
    print(f"[F08-monitor] Baud: {baud}")
    print(f"[F08-monitor] Duración: {post_wait_s:.2f}s")

    ser = serial.Serial(port, baud, timeout=0)
    time.sleep(2.0)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    logf = open(log_path, "w")

    stopped_by_user = False

    try:
        end_time = time.monotonic() + post_wait_s
        while time.monotonic() < end_time:
            pending = getattr(ser, "in_waiting", 0)
            if pending and pending > 0:
                data = ser.read(pending)
                if data:
                    text = data.decode("utf-8", errors="ignore")
                    logf.write(text)
                    logf.flush()
            else:
                time.sleep(0.05)

    except KeyboardInterrupt:
        stopped_by_user = True
        print("\n[F08-monitor] Captura interrumpida por usuario (Ctrl+C). Continuando flujo.")

    finally:
        logf.close()
        ser.close()

    if stopped_by_user:
        print("[F08-monitor] Finalizado por usuario.")
    else:
        print("\n[F08-monitor] Finalizado correctamente.")


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True)
    parser.add_argument("--mode", choices=["serial", "memory"], default="serial")
    parser.add_argument("--port", default=None)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--drain-seconds", type=float, default=None)
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--no-clean-build", action="store_true")
    args = parser.parse_args()

    try:
        variant = args.variant
        mode = args.mode

        variant_dir = get_variant_dir(PHASE, variant)

        edge_cfg_path = variant_dir / "08_edge_run_config.yaml"
        if not edge_cfg_path.exists():
            raise RuntimeError("[F08] 08_edge_run_config.yaml no encontrado.")

        edge_cfg = yaml.safe_load(edge_cfg_path.read_text())
        platform = str(edge_cfg.get("platform", "")).strip().lower()
        if not platform:
            raise RuntimeError("[F08] platform no definido en 08_edge_run_config.yaml")

        project_dir = resolve_project_dir(variant_dir, edge_cfg, platform)

        geom = edge_cfg.get("geometry", {})
        drain_cfg = edge_cfg.get("drain", {})

        OW = geom.get("OW", 0)
        LT = geom.get("LT", 0)
        mti_ms, legacy_mti = resolve_max_mti_ms(edge_cfg)
        tu_ms = resolve_tu_ms(edge_cfg)
        recommended = drain_cfg.get("recommended_drain_seconds") if isinstance(drain_cfg, dict) else None

        tunit_s = float(tu_ms) / 1000.0 if tu_ms else 1.0

        if args.drain_seconds is not None:
            post_wait_s = args.drain_seconds
        elif recommended is not None:
            post_wait_s = float(recommended)
        else:
            post_wait_s = max(5.0, float((OW or 0) + (LT or 0)) * tunit_s)

        if mti_ms is not None:
            min_post_wait_s = float(OW or 0) * tunit_s + float(mti_ms) / 1000.0
        else:
            min_post_wait_s = float((OW or 0) + float(legacy_mti or 0)) * tunit_s

        if post_wait_s < min_post_wait_s:
            print(
                f"[F08] Ajustando drain a minimo OW+MTI(ms): {post_wait_s:.2f}s -> {min_post_wait_s:.2f}s"
            )
            post_wait_s = min_post_wait_s

        print(f"[F08] post_wait_s = {post_wait_s:.2f}s")

        port = args.port
        if not args.build_only:
            if not port:
                detected = auto_detect_port()

                if detected is None:
                    raise RuntimeError(
                        "[F08] No se detecta ningún puerto serie. "
                        "Conecta la placa o usa --port."
                    )

                if detected == "MULTIPLE":
                    raise RuntimeError(
                        "[F08] Múltiples puertos detectados. Especifica --port."
                    )

                port = detected
                print(f"[F08] Puerto autodetectado: {port}")

        build_log = variant_dir / "08_esp_build_log.txt"
        flash_log = variant_dir / "08_esp_flash_log.txt"
        monitor_log = variant_dir / "08_esp_monitor_log.txt"

        dataset_csv = variant_dir / "08_input_dataset.csv"

        if platform != "esp32":
            run_platform_runner_flow(
                platform=platform,
                variant=variant,
                variant_dir=variant_dir,
                edge_cfg_path=edge_cfg_path,
                edge_cfg=edge_cfg,
                project_dir=project_dir,
                build_log=build_log,
                flash_log=flash_log,
                monitor_log=monitor_log,
                dataset_csv=dataset_csv,
                args=args,
            )
            return

        esp_project_dir = project_dir

        print("\n=== BUILD ===")
        if not args.no_clean_build:
            build_dir = esp_project_dir / "build"
            if build_dir.exists():
                shutil.rmtree(build_dir)
                print(f"[F08] build limpio: {build_dir}")

        sync_generated_sources_for_build(esp_project_dir)
        sanitize_sdkconfig_for_docker(esp_project_dir)
        docker_memory_limit = resolve_docker_memory_limit()
        docker_memory_swap = resolve_docker_memory_swap()
        docker_cpus = resolve_docker_cpus()

        if docker_memory_limit:
            print(f"[F08] Docker memory limit por defecto: {docker_memory_limit}")
        if docker_memory_swap:
            print(f"[F08] Docker memory-swap: {docker_memory_swap}")
        if docker_cpus:
            print(f"[F08] Docker cpus: {docker_cpus}")

        build_jobs = os.environ.get("F08_DOCKER_BUILD_JOBS", "1")
        run_idf_and_log(
            ["build"],
            build_log,
            esp_project_dir=esp_project_dir,
            cmake_parallel_level=build_jobs,
            docker_memory_limit=docker_memory_limit,
            docker_memory_swap=docker_memory_swap,
            docker_cpus=docker_cpus,
        )

        export_platform_build_artifacts(variant_dir, esp_project_dir, platform)

        if args.build_only:
            print("\n[F08] Build-only completado con éxito.")
            return

        print("\n=== FLASH ===")
        flash_portable(
            port=port,
            flash_log=flash_log,
            esp_project_dir=esp_project_dir,
            docker_memory_limit=docker_memory_limit,
            docker_memory_swap=docker_memory_swap,
            docker_cpus=docker_cpus,
        )

        print("\n=== RUN ===")

        if mode == "serial":
            serial_send_and_monitor(
                port=port,
                baud=args.baud,
                input_file=dataset_csv,
                log_path=monitor_log,
                tunit_ms=tu_ms,
                post_wait_s=post_wait_s,
            )
        else:
            serial_monitor_only(
                port=port,
                baud=args.baud,
                log_path=monitor_log,
                post_wait_s=post_wait_s,
            )

        print("\n[F08] Flash-run completado con éxito.")
    except KeyboardInterrupt:
        print(
            "\n[F08] Ejecución interrumpida por usuario (Ctrl+C). "
            "Se conservan logs parciales para análisis en F084."
        )
        return


if __name__ == "__main__":
    main()
    