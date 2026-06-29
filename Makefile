ifeq ($(OS),Windows_NT)
  SHELL := C:/PROGRA~1/Git/bin/bash.exe
else
  SHELL := /bin/bash
endif

ifeq ($(OS),Windows_NT)
  PYTHON_LOCAL ?= python
else
  PYTHON_LOCAL ?= python3.11
endif

F56_GPU ?= false

ifeq ($(OS),Windows_NT)
  PYTHON_LOCAL_FOUND := $(shell powershell.exe -NoProfile -Command "if (Get-Command $(PYTHON_LOCAL) -ErrorAction SilentlyContinue) { 'yes' }")
else
  PYTHON_LOCAL_FOUND := $(shell command -v $(PYTHON_LOCAL) 2>/dev/null)
endif

ifeq ($(PYTHON_LOCAL_FOUND),)
  $(error python3.11 not found. Please install it before running make setup)
endif

$(info [INFO] Using local Python interpreter: $(PYTHON_LOCAL))

ifneq ("$(wildcard .env)","")
  include .env
  export
endif

ifneq ("$(wildcard .mlops4ofp/env.sh)","")
  include .mlops4ofp/env.sh
  export
endif

############################################
# SETUP — MLOps4OFP (one-time configuration)
############################################

SETUP_PY = setup/setup.py
SETUP_ENV = .mlops4ofp/env.sh
SETUP_CFG ?=

help-setup:
	@echo "=============================================="
	@echo " MLOps4OFP — PROJECT SETUP"
	@echo "=============================================="
	@echo ""
	@echo "This process is executed ONLY ONCE per project copy."
	@echo ""
	@echo "Available flows:"
	@echo ""
	@echo "  make setup SETUP_CFG=setup/local.yaml"
	@echo "      Non-interactive setup from YAML file"
	@echo ""
	@echo "  make setup SETUP_CFG=setup/remote.yaml"
	@echo "      Non-interactive setup from YAML file"
	@echo ""
	@echo "  make check-setup"
	@echo "      Verify that the setup is valid and the environment is correctly configured"
	@echo ""
	@echo "  make clean-setup"
	@echo "      Remove the setup configuration and all generated artifacts, allowing to start from scratch"
	@echo ""
	@echo "=============================================="

setup:
	@echo "==> Running project setup with configuration: $(SETUP_CFG)"
ifndef SETUP_CFG
	$(error You must specify SETUP_CFG=<file.yaml> (e.g., setup/local.yaml or setup/remote.yaml))
endif
	@$(PYTHON_LOCAL) -m pip install pyyaml==6.0.1
	@$(PYTHON_LOCAL) $(SETUP_PY) --config $(SETUP_CFG)
	@mkdir -p .mlops4ofp
	@cp $(SETUP_CFG) .mlops4ofp/setup.yaml
	@set -e; \
	MODE=$$($(PYTHON_LOCAL) -c 'import yaml,pathlib; cfg=yaml.safe_load(pathlib.Path(".mlops4ofp/setup.yaml").read_text()); print(cfg.get("git",{}).get("mode","none"))'); \
	if [ "$$MODE" = "custom" ]; then \
		PUBLISH_REMOTE=$$($(PYTHON_LOCAL) -c 'import yaml,pathlib; cfg=yaml.safe_load(pathlib.Path(".mlops4ofp/setup.yaml").read_text()); print(cfg.get("git",{}).get("publish_remote_name","publish"))'); \
		PUBLISH_BRANCH=$$($(PYTHON_LOCAL) -c 'import yaml,pathlib; cfg=yaml.safe_load(pathlib.Path(".mlops4ofp/setup.yaml").read_text()); print(cfg.get("git",{}).get("branch","main"))'); \
		echo "==> Committing setup artifacts"; \
		git add .mlops4ofp/ .dvc/config 2>/dev/null || true; \
		git commit -m "setup: initialize project configuration" 2>/dev/null || echo "[INFO] Nothing new to commit"; \
		echo "==> Pushing to $$PUBLISH_REMOTE HEAD:$$PUBLISH_BRANCH"; \
		git push "$$PUBLISH_REMOTE" "HEAD:$$PUBLISH_BRANCH"; \
	else \
		echo "[INFO] git.mode=$$MODE — skipping commit and push"; \
	fi


check-setup:
	@echo "==> Verifying base environment configuration"
	@$(PYTHON) setup/check_env.py
	@echo "==> Verifying project setup configuration"
	@$(PYTHON) setup/check_setup.py

clean-setup:
	@echo "==> Removing MLflow associated with the project (if exists)"
	@$(PYTHON_LOCAL) -c 'import yaml,pathlib,os,shutil,sys;cfg_path=pathlib.Path(".mlops4ofp/setup.yaml");sys.exit(0) if not cfg_path.exists() else None;cfg=yaml.safe_load(cfg_path.read_text());ml=cfg.get("mlflow",{});sys.exit(0) if not ml.get("enabled",False) else None;uri=ml.get("tracking_uri","");(print(f"[INFO] Removing local MLflow at {path}") or shutil.rmtree(path)) if uri.startswith("file:") and os.path.exists(path:=uri.replace("file:","")) else (exec("import mlflow;from mlflow.tracking import MlflowClient;mlflow.set_tracking_uri(uri) if uri else None;client=MlflowClient();[print(f\"[INFO] Removing remote experiment {e.name}\") or client.delete_experiment(e.experiment_id) for e in client.search_experiments() if e.name.startswith(\"F05_\")]") if uri else None)' 2>/dev/null || true
	@echo "==> Removing complete ML project environment"
# 	@rm -rf .mlops4ofp .dvc .dvc_storage local_dvc_store .venv executions
	@rm -rf .mlops4ofp .dvc .dvc_storage local_dvc_store executions
	@echo "[OK] ML project reinitialized. Run 'make setup' to rebuild base structure."


ifeq ($(OS),Windows_NT)
  PYTHON := .venv/Scripts/python.exe
  DVC := .venv/Scripts/dvc.exe
  JUPYTER := .venv/Scripts/jupyter.exe
 
  # Docker on Git Bash can rewrite container paths like /workspace into
  # C:/Program Files/Git/workspace. Use //-prefixed container paths to avoid
  # MSYS path conversion and keep a valid container workdir.
  DOCKER_HOST_PWD := $(shell pwd -W 2>/dev/null)
  ifeq ($(strip $(DOCKER_HOST_PWD)),)
    DOCKER_HOST_PWD := $(PWD)
  endif
  DOCKER_WORKSPACE_PATH := //workspace
  DOCKER_PROJECT_PATH := //project
else
  MLOPS_VENV_PATH ?= .venv
  ifneq ("$(wildcard $(MLOPS_VENV_PATH)/bin/python3)","")
    PYTHON := $(MLOPS_VENV_PATH)/bin/python3
    DVC := $(MLOPS_VENV_PATH)/bin/dvc
    JUPYTER := $(MLOPS_VENV_PATH)/bin/jupyter
  else
    PYTHON := python3
    DVC := dvc
    JUPYTER := jupyter
  endif
  DOCKER_HOST_PWD := $(PWD)
  DOCKER_WORKSPACE_PATH := /workspace
  DOCKER_PROJECT_PATH := /project
endif

ifeq ($(OS),Windows_NT)
	DOCKER_HOST_USER_ARGS :=
else
	DOCKER_HOST_USER_ARGS := --user $$(id -u):$$(id -g)
endif

$(info [INFO] Using Python interpreter in venv: $(PYTHON))

############################################
# Generic targets by phase
############################################

############################################
# Generic targets by phase
############################################

check-variant-format:
	@test -n "$(VARIANT)" || (echo "[ERROR] You must specify VARIANT=vY_XXXX"; exit 1)
	@if ! echo $(VARIANT) | grep -Eq '^(v[0-9]_[0-9]{4}|v?[0-9]{1,4})$$'; then \
	    echo "[ERROR] Incorrect format for VARIANT: $(VARIANT)"; \
	    echo "        Allowed forms: vY_XXXX, vNNNN, vNNN, vNN, vN, NNNN, NNN, NN, N"; \
	    echo "        Example for phase f01_*: v1_0001, v0001, v001, v01, v1, 1"; \
	    exit 1; \
	fi

# Normalize VARIANT to canonical format vY_XXXX, where Y is inferred from PHASE (f0Y_*).
# Accepted inputs:
#   - canonical: vY_XXXX
#   - shorthand: vNNNN | vNNN | vNN | vN | NNNN | NNN | NN | N
NORMALIZE_VARIANT = bash -eu -c 'phase="$$1"; variant="$$2"; \
if [[ "$$phase" =~ ^f([0-9]{2})(_|$$) ]]; then \
	phase_digit=$$((10\#$${BASH_REMATCH[1]})); \
else \
	echo "[ERROR] PHASE is required to normalize VARIANT" >&2; exit 1; \
fi; \
if [[ "$$variant" =~ ^v([0-9])_([0-9]{4})$$ ]]; then \
	if [[ "$${BASH_REMATCH[1]}" != "$$phase_digit" ]]; then \
		echo "[ERROR] Incorrect phase marker in VARIANT=$$variant for PHASE=$$phase; expected v$${phase_digit}_XXXX" >&2; exit 1; \
	fi; \
	echo "v$${BASH_REMATCH[1]}_$${BASH_REMATCH[2]}"; \
	exit 0; \
fi; \
if [[ "$$variant" =~ ^v?([0-9]{1,4})$$ ]]; then \
	num=$$((10\#$${BASH_REMATCH[1]})); \
	printf "v%s_%04d\n" "$$phase_digit" "$$num"; \
	exit 0; \
fi; \
echo "[ERROR] Incorrect format for VARIANT: $$variant. Use vY_XXXX or shorthand vNNNN/NNNN" >&2; exit 1' _ "$(PHASE)" "$(VARIANT)"

# Normalize VARIANT for an explicit phase value. Used by targets such as script5
# that do not define PHASE as a make variable.
NORMALIZE_VARIANT_FOR_PHASE = bash -eu -c 'phase="$$1"; variant="$$2"; \
if [[ "$$phase" =~ ^f([0-9]{2})(_|$$) ]]; then \
	phase_digit=$$((10\#$${BASH_REMATCH[1]})); \
else \
	echo "[ERROR] PHASE is required to normalize VARIANT" >&2; exit 1; \
fi; \
if [[ "$$variant" =~ ^v([0-9])_([0-9]{4})$$ ]]; then \
	if [[ "$${BASH_REMATCH[1]}" != "$$phase_digit" ]]; then \
		echo "[ERROR] Incorrect phase marker in VARIANT=$$variant for PHASE=$$phase; expected v$$phase_digit_XXXX" >&2; exit 1; \
	fi; \
	echo "v$${BASH_REMATCH[1]}_$${BASH_REMATCH[2]}"; \
	exit 0; \
fi; \
if [[ "$$variant" =~ ^v?([0-9]{1,4})$$ ]]; then \
	num=$$((10\#$${BASH_REMATCH[1]})); \
	printf "v%s_%04d\n" "$$phase_digit" "$$num"; \
	exit 0; \
fi; \
echo "[ERROR] Incorrect format for VARIANT: $$variant. Use vY_XXXX or shorthand vNNNN/NNNN" >&2; exit 1' _

############################################
# Internal helpers (inline Python, no extra script)
############################################

# Centralized lifecycle-state mapping (single point of change).
LIFECYCLE_STATE_CREATED := VARIANT_CREATED
LIFECYCLE_STATE_EXECUTION_RUNNING := EXECUTION_RUNNING
LIFECYCLE_STATE_EXECUTION_COMPLETED := EXECUTION_COMPLETED
LIFECYCLE_STATE_EXECUTION_FAILED := EXECUTION_FAILED

# Resolve parent phase + parent(s) from params.yaml of a created variant.
# Outputs shell assignments:
#   PARENT_PHASE="f01_explore"
#   PARENTS="v109"
# or for F08:
#   PARENT_PHASE="f07_modval"
#   PARENTS="v700 v701 v702"
RESOLVE_PARENT_INFO = $(PYTHON) -c "import yaml; from pathlib import Path; from scripts.core.params_manager import infer_parent_phase, load_schema; phase='$(PHASE)'; params_path='$(VARIANTS_DIR)/$(VARIANT)/params.yaml'; data=yaml.safe_load(open(params_path).read()) or {}; parent=data.get('parent'); params=data.get('parameters', {}) or {}; pv=params.get('parent_variant'); parents=(pv if isinstance(pv, list) else ([pv] if isinstance(pv, str) and pv else [])) or params.get('parents', []) or []; schema=load_schema(); parent_phase=infer_parent_phase(schema, phase) or ''; resolved = [parent] if parent else (parents if parents else []); print('PARENT_PHASE=\"%s\"' % parent_phase); print('PARENTS=\"%s\"' % ' '.join(resolved))"

# Create creation_context.yaml with commit + digest of watched paths
define WRITE_CREATION_CONTEXT
    $(PYTHON) - "$(VARIANTS_DIR)/$(VARIANT)/creation_context.yaml" "$(PHASE)" <<'PY'
import sys, yaml, hashlib, subprocess
from pathlib import Path
from datetime import datetime, timezone

out = Path(sys.argv[1])
phase = sys.argv[2]

watch_paths = ["scripts", "scripts/traceability_schema.yaml"]
if phase in ("f07_modval", "f08_sysval"):
    watch_paths.insert(1, "edge")

def digest(paths):
    h = hashlib.sha256()
    files = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            continue
        if path.is_file():
            files.append(path)
        else:
            files.extend(sorted(x for x in path.rglob("*") if x.is_file()))
    for f in sorted(files):
        h.update(str(f).encode())
        h.update(f.read_bytes())
    return h.hexdigest()

ctx = {
    "created_at": datetime.now(timezone.utc).isoformat(),
    "created_git_commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip(),
    "watched_paths": watch_paths,
    "watched_digest": digest(watch_paths),
}
with out.open("w") as fh:
    yaml.safe_dump(ctx, fh, sort_keys=False)
PY
endef

# Update lifecycle state in metadata.yaml for a concrete phase/variant.
# Usage:
#   $(UPDATE_VARIANT_STATE) <phase> <variant> <state>
UPDATE_VARIANT_STATE = $(PYTHON) -c 'import sys, os, yaml; from pathlib import Path; from datetime import datetime, timezone; phase, variant, state = sys.argv[1], sys.argv[2], sys.argv[3]; variant_dir = Path("executions") / phase / variant; meta_path = variant_dir / "metadata.yaml"; data = {}; \
variant_dir.exists() or sys.exit(0); \
data = yaml.safe_load(meta_path.read_text()) if meta_path.exists() else {}; \
data = data if isinstance(data, dict) else {}; \
data.setdefault("params_path", str((variant_dir / "params.yaml").as_posix())); \
data.setdefault("created_at", datetime.now(timezone.utc).isoformat()); \
data["lifecycle_state"] = state; \
data["lifecycle_updated_at"] = datetime.now(timezone.utc).isoformat(); \
data["runner"] = os.environ.get("MLOPS_RUNNER") or os.popen("whoami").read().strip(); \
data.setdefault("registred", "none"); \
preferred = ["created_at", "params_path", "lifecycle_state", "lifecycle_updated_at", "verified", "verified_updated_at", "registred", "runner"]; \
ordered = {k: data[k] for k in preferred if k in data}; \
ordered.update({k: v for k, v in data.items() if k not in ordered}); \
data = ordered; \
meta_path.write_text(yaml.safe_dump(data, sort_keys=False))'

# Update verification status in metadata.yaml for a concrete phase/variant.
# Usage:
#   $(UPDATE_VARIANT_VERIFIED) <phase> <variant> <true|false|none>
UPDATE_VARIANT_VERIFIED = $(PYTHON) -c 'import sys, yaml; from pathlib import Path; from datetime import datetime, timezone; phase, variant, verified_raw = sys.argv[1], sys.argv[2], sys.argv[3].lower(); variant_dir = Path("executions") / phase / variant; meta_path = variant_dir / "metadata.yaml"; data = {}; \
variant_dir.exists() or sys.exit(0); \
data = yaml.safe_load(meta_path.read_text()) if meta_path.exists() else {}; \
data = data if isinstance(data, dict) else {}; \
data.setdefault("params_path", str((variant_dir / "params.yaml").as_posix())); \
data.setdefault("created_at", datetime.now(timezone.utc).isoformat()); \
verified_map = {"true": True, "false": False, "none": "none", "not_checked": "none", "no": "none", "no_hecho": "none"}; \
data["verified"] = verified_map.get(verified_raw, "none"); \
data["verified_updated_at"] = datetime.now(timezone.utc).isoformat(); \
data.setdefault("registred", "none"); \
preferred = ["created_at", "params_path", "lifecycle_state", "lifecycle_updated_at", "verified", "verified_updated_at", "registred", "runner"]; \
ordered = {k: data[k] for k in preferred if k in data}; \
ordered.update({k: v for k, v in data.items() if k not in ordered}); \
data = ordered; \
meta_path.write_text(yaml.safe_dump(data, sort_keys=False))'

# Update registration status in metadata.yaml for a concrete phase/variant.
# Usage:
#   $(UPDATE_VARIANT_REGISTRED) <phase> <variant> <true|false|none>
UPDATE_VARIANT_REGISTRED = $(PYTHON) -c 'import sys, yaml; from pathlib import Path; from datetime import datetime, timezone; phase, variant, registred_raw = sys.argv[1], sys.argv[2], sys.argv[3].lower(); variant_dir = Path("executions") / phase / variant; meta_path = variant_dir / "metadata.yaml"; data = {}; \
variant_dir.exists() or sys.exit(0); \
data = yaml.safe_load(meta_path.read_text()) if meta_path.exists() else {}; \
data = data if isinstance(data, dict) else {}; \
data.setdefault("params_path", str((variant_dir / "params.yaml").as_posix())); \
data.setdefault("created_at", datetime.now(timezone.utc).isoformat()); \
data.setdefault("verified", "none"); \
registred_map = {"true": True, "false": False, "none": "none", "not_checked": "none", "no": "none", "no_hecho": "none"}; \
data["registred"] = registred_map.get(registred_raw, "none"); \
preferred = ["created_at", "params_path", "lifecycle_state", "lifecycle_updated_at", "verified", "verified_updated_at", "registred", "runner"]; \
ordered = {k: data[k] for k in preferred if k in data}; \
ordered.update({k: v for k, v in data.items() if k not in ordered}); \
data = ordered; \
meta_path.write_text(yaml.safe_dump(data, sort_keys=False))'


script-run-generic: check-variant-format
	@set -eu; \
	VARIANT_NORM="$$($(NORMALIZE_VARIANT))"; \
	$(UPDATE_VARIANT_VERIFIED) $(PHASE) $$VARIANT_NORM none >/dev/null 2>&1 || true; \
	$(UPDATE_VARIANT_STATE) $(PHASE) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_RUNNING) >/dev/null 2>&1 || true; \
	echo "==> Regenerating lineage dashboard"; \
	$(MAKE) --no-print-directory generate_lineage || true; \
	echo "==> Running script PHASE $(PHASE) for variant $$VARIANT_NORM"; \
	$(PYTHON) -m $(SCRIPT_MODULE) --variant $$VARIANT_NORM || { \
		$(UPDATE_VARIANT_STATE) $(PHASE) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_FAILED) >/dev/null 2>&1 || true; \
		echo "==> Regenerating lineage dashboard"; \
		$(MAKE) --no-print-directory generate_lineage || true; \
		exit 1; \
	}; \
	$(UPDATE_VARIANT_STATE) $(PHASE) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_COMPLETED) >/dev/null 2>&1 || true; \
	echo "==> Regenerating lineage dashboard"; \
	$(MAKE) --no-print-directory generate_lineage || true

variant-generic: check-variant-format
	@set -eu; \
	VARIANT_NORM="$$($(NORMALIZE_VARIANT))"; \
	echo "==> Creando variante $(PHASE):$$VARIANT_NORM"; \
	$(PYTHON) -m scripts.core.params_manager create \
		--phase $(PHASE) \
		--variant $$VARIANT_NORM \
		--set-args "$(strip $(EXTRA_FLAGS))"; \
	$(UPDATE_VARIANT_REGISTRED) $(PHASE) $$VARIANT_NORM none >/dev/null 2>&1 || true; \
	$(UPDATE_VARIANT_VERIFIED) $(PHASE) $$VARIANT_NORM none >/dev/null 2>&1 || true; \
	$(UPDATE_VARIANT_STATE) $(PHASE) $$VARIANT_NORM $(LIFECYCLE_STATE_CREATED) >/dev/null 2>&1 || true; \
	echo "[OK] Variante creada: $(PHASE):$$VARIANT_NORM"; \
	echo "==> Regenerating lineage dashboard"; \
	$(MAKE) --no-print-directory generate_lineage || true

############################################
# Register variant
############################################

register-generic: check-variant-format
	@set -eu; \
	VARIANT_NORM="$$($(NORMALIZE_VARIANT))"; \
	$(UPDATE_VARIANT_REGISTRED) $(PHASE) $$VARIANT_NORM none >/dev/null 2>&1 || true; \
	echo "==> Regenerating lineage dashboard"; \
	$(MAKE) --no-print-directory generate_lineage || true; \
	echo "==> Registering $(PHASE):$$VARIANT_NORM"; \
	echo "==> Validating + auditing variant"; \
	$(PYTHON) -m scripts.core.traceability validate-variant \
		--phase $(PHASE) \
		--variant $$VARIANT_NORM || { $(UPDATE_VARIANT_REGISTRED) $(PHASE) $$VARIANT_NORM false >/dev/null 2>&1 || true; echo "==> Regenerating lineage dashboard"; $(MAKE) --no-print-directory generate_lineage || true; exit 1; }; \
	MODE=$$($(PYTHON) -c "import yaml, pathlib; cfg=yaml.safe_load(pathlib.Path('.mlops4ofp/setup.yaml').read_text()); print(cfg.get('git',{}).get('mode','none'))"); \
	PUBLISH_REMOTE=$$($(PYTHON) -c "import yaml, pathlib; cfg=yaml.safe_load(pathlib.Path('.mlops4ofp/setup.yaml').read_text()); print(cfg.get('git',{}).get('publish_remote_name','publish'))"); \
	PUBLISH_BRANCH=$$($(PYTHON) -c "import yaml, pathlib; cfg=yaml.safe_load(pathlib.Path('.mlops4ofp/setup.yaml').read_text()); print(cfg.get('git',{}).get('branch','main'))"); \
	echo "==> Registering DVC artifacts"; \
	for ext in $(DVC_EXTS); do \
		$(DVC) add "$(VARIANTS_DIR)/$$VARIANT_NORM"/*.$$ext 2>/dev/null || true; \
	done; \
	if [ "$$MODE" = "custom" ]; then \
		echo "==> Adding files to Git"; \
		git add "$(VARIANTS_DIR)/$$VARIANT_NORM" 2>/dev/null || true; \
		git add "$(VARIANTS_DIR)/$$VARIANT_NORM"/*.dvc 2>/dev/null || true; \
		git add dvc.yaml dvc.lock 2>/dev/null || true; \
		echo "==> Commit"; \
		git commit -m "register $(PHASE):$$VARIANT_NORM" || true; \
		echo "==> Push (if configured)"; \
		git push "$$PUBLISH_REMOTE" "HEAD:$$PUBLISH_BRANCH" || true; \
	elif [ "$$MODE" = "none" ]; then \
		echo "[INFO] Local-only mode: skipping git add/commit/push"; \
	else \
		echo "[ERROR] Invalid or unconfigured git mode: $$MODE"; $(UPDATE_VARIANT_REGISTRED) $(PHASE) $$VARIANT_NORM false >/dev/null 2>&1 || true; echo "==> Regenerating lineage dashboard"; $(MAKE) --no-print-directory generate_lineage || true; exit 1; \
	fi; \
	echo "==> DVC push"; \
	$(DVC) push -r storage || true; \
	$(UPDATE_VARIANT_REGISTRED) $(PHASE) $$VARIANT_NORM true >/dev/null 2>&1 || true; \
	echo "[OK] Registered $(PHASE):$$VARIANT_NORM"; \
	echo "==> Regenerating lineage dashboard"; \
	$(MAKE) --no-print-directory generate_lineage || true

############################################
# Remove variant
############################################

remove-generic: check-variant-format
	@set -eu; \
	VARIANT_NORM="$$($(NORMALIZE_VARIANT))"; \
	echo "==> Checking if variant $(PHASE):$$VARIANT_NORM has children…"; \
	$(PYTHON) -m scripts.core.traceability can-delete --phase $(PHASE) --variant $$VARIANT_NORM; \
	VAR_DIR="$(VARIANTS_DIR)/$$VARIANT_NORM"; \
	if [ -d "$$VAR_DIR" ]; then \
		echo "==> Removing associated DVC artifacts (if any)"; \
		for f in "$$VAR_DIR"/*.dvc; do \
			if [ -f "$$f" ]; then \
				$(DVC) remove "$$f" || true; \
			fi; \
		done; \
		echo "==> Removing complete variant folder"; \
		rm -rf "$$VAR_DIR"; \
	fi; \
	MODE=$$($(PYTHON) -c "import yaml, pathlib; cfg=yaml.safe_load(pathlib.Path('.mlops4ofp/setup.yaml').read_text()); print(cfg.get('git',{}).get('mode','none'))"); \
	PUBLISH_REMOTE=$$($(PYTHON) -c "import yaml, pathlib; cfg=yaml.safe_load(pathlib.Path('.mlops4ofp/setup.yaml').read_text()); print(cfg.get('git',{}).get('publish_remote_name','publish'))"); \
	PUBLISH_BRANCH=$$($(PYTHON) -c "import yaml, pathlib; cfg=yaml.safe_load(pathlib.Path('.mlops4ofp/setup.yaml').read_text()); print(cfg.get('git',{}).get('branch','main'))"); \
	if [ "$$MODE" = "custom" ]; then \
		echo "==> Adding deletion changes to Git"; \
		git add "$(VARIANTS_DIR)" 2>/dev/null || true; \
		git add dvc.yaml dvc.lock 2>/dev/null || true; \
		git commit -m "remove variant: $(PHASE) $$VARIANT_NORM" || true; \
		git push "$$PUBLISH_REMOTE" "HEAD:$$PUBLISH_BRANCH" || echo "[WARN] git push $$PUBLISH_REMOTE HEAD:$$PUBLISH_BRANCH failed"; \
	elif [ "$$MODE" = "none" ]; then \
		echo "[INFO] Local-only mode: skipping git add/commit/push"; \
	else \
		echo "[ERROR] Invalid or unconfigured git mode"; exit 1; \
	fi; \
	echo "==> Push DVC to propagate deletion"; \
	$(DVC) push -r storage || echo "[WARN] dvc push failed"; \
	echo "[OK] Variant $(PHASE):$$VARIANT_NORM completely removed."; \
	echo "==> Regenerating lineage dashboard"; \
	$(MAKE) generate_lineage || true

############################################
# Check results
############################################
CHECK_FILE = "makefile_check_phases.yml"
check-results-generic: check-variant-format
	@test -n "$(PHASE)" || (echo "[ERROR] PHASE not defined"; exit 1)
	@test -n "$(VARIANTS_DIR)" || (echo "[ERROR] VARIANTS_DIR not defined"; exit 1)
	@test -n "$(VARIANT)" || (echo "[ERROR] VARIANT not defined"; exit 1)

	@VARIANT_NORM="$$($(NORMALIZE_VARIANT))"; \
	$(UPDATE_VARIANT_VERIFIED) $(PHASE) $$VARIANT_NORM none >/dev/null 2>&1 || true; \
	echo "==> Regenerating lineage dashboard"; \
	$(MAKE) --no-print-directory generate_lineage || true; \
	if ! $(PYTHON) -m scripts.core.phase_checker \
		--spec $(CHECK_FILE) \
		--phase $(PHASE) \
		--variant-dir "$(VARIANTS_DIR)/$$VARIANT_NORM"; then \
		$(UPDATE_VARIANT_VERIFIED) $(PHASE) $$VARIANT_NORM false >/dev/null 2>&1 || true; \
		echo "==> Regenerating lineage dashboard"; \
		$(MAKE) --no-print-directory generate_lineage || true; \
		echo "[ERROR] Phase checker validation failed"; \
		exit 1; \
	fi; \
	$(UPDATE_VARIANT_VERIFIED) $(PHASE) $$VARIANT_NORM true >/dev/null 2>&1 || true; \
	echo "==> Regenerating lineage dashboard"; \
	$(MAKE) --no-print-directory generate_lineage || true

############################################
# Remove all variants from phase
############################################

remove-phase-all:
	@echo "==> Removing ALL variants of phase $(PHASE) (SAFE mode: only if no children dependencies)"
	@test -d "$(VARIANTS_DIR)" || \
	  (echo "[INFO] $(VARIANTS_DIR) does not exist. Nothing to delete."; exit 0)
	@for v in $$(ls $(VARIANTS_DIR) | grep '^v[0-9]_[0-9]\{4\}$$'); do \
	  echo "----> Removing $(PHASE):$$v"; \
	  $(MAKE) remove-generic PHASE=$(PHASE) VARIANTS_DIR=$(VARIANTS_DIR) VARIANT=$$v || exit 1; \
	done
	@echo "[OK] Phase $(PHASE) completely removed (SAFE mode: only if no children dependencies)"

PHASE1 = f01_explore
SCRIPT1_MODULE = scripts.phases.f01_explore
VARIANTS_DIR1 = executions/$(PHASE1)

variant1: check-variant-format
	@test -n "$(RAW)" || (echo "[ERROR] You must specify RAW=/path/to/dataset"; exit 1)
	@test -n "$(CLEANING)" || (echo "[ERROR] You must specify CLEANING=none|basic|strict"; exit 1)

	@$(MAKE) variant-generic \
		PHASE=$(PHASE1) \
		VARIANTS_DIR=$(VARIANTS_DIR1) \
		VARIANT=$(VARIANT) \
		EXTRA_FLAGS="\
			raw_path=$(RAW) \
			cleaning=$(CLEANING) \
			$(if $(strip $(NAN_VALUES)),nan_values=$(NAN_VALUES)) \
			$(if $(strip $(ERROR_VALUES)),error_values=$(ERROR_VALUES)) \
			$(if $(strip $(FIRST_LINE)),first_line=$(FIRST_LINE)) \
			$(if $(strip $(MAX_LINES)),max_lines=$(MAX_LINES))"

script1:
	$(MAKE) script-run-generic PHASE=$(PHASE1) SCRIPT_MODULE=$(SCRIPT1_MODULE) VARIANT=$(VARIANT)

check1: check-variant-format
	$(MAKE) check-results-generic \
		PHASE=$(PHASE1) \
		VARIANTS_DIR=$(VARIANTS_DIR1) \
		VARIANT=$(VARIANT)

register1: check-variant-format
	$(MAKE) register-generic \
		PHASE=$(PHASE1) \
		VARIANTS_DIR=$(VARIANTS_DIR1) \
		DVC_EXTS="parquet" \
		VARIANT=$(VARIANT)

remove1: check-variant-format
	$(MAKE) remove-generic PHASE=$(PHASE1) VARIANTS_DIR=$(VARIANTS_DIR1) VARIANT=$(VARIANT)

remove1-all:
	$(MAKE) remove-phase-all PHASE=$(PHASE1) VARIANTS_DIR=$(VARIANTS_DIR1)

help1:
	@echo "==============================================="
	@echo " 01 — EXPLORE"
	@echo "==============================================="
	@echo ""
	@echo " Create:"
	@echo "   make variant1 VARIANT=v001 RAW=./data/raw.csv \\"
	@echo "       CLEANING=basic [NAN_VALUES='[-999999]'] [ERROR_VALUES='{}'] \\" 
	@echo "       [MAX_LINES=10000] [FIRST_LINE=1]"
	@echo ""
	@echo " Execution:"
	@echo "   make script1 VARIANT=v001"
	@echo ""
	@echo " Checking:"
	@echo "   make check1 VARIANT=v001"
	@echo ""
	@echo " Register:"
	@echo "   make register1 VARIANT=v001"
	@echo ""
	@echo " Remove: (only if no children variants)"
	@echo "   make remove1 VARIANT=v001"
	@echo ""
	@echo "==============================================="


PHASE2 = f02_events
SCRIPT2_MODULE = scripts.phases.f02_events
VARIANTS_DIR2 = executions/$(PHASE2)

variant2: check-variant-format
	@test -n "$(PARENT)"   || (echo "[ERROR] You must specify PARENT=vY_XXXX (parent F01 variant)"; exit 1)
	@test -n "$(MEASURE)"  || (echo "[ERROR] You must specify MEASURE=<column_name>"; exit 1)
	@$(eval MEASURE_COLS := $(shell $(PYTHON) -c "import yaml; d=yaml.safe_load(open('executions/f01_explore/$(PARENT)/outputs.yaml', encoding='utf-8')); print(' '.join(d.get('exports', {}).get('measure_cols', [])))"))
	@if ! echo "$(MEASURE_COLS)" | grep -qw "$(MEASURE)"; then \
	  echo "[ERROR] Invalid MEASURE. Must be one of: $(MEASURE_COLS)"; exit 1; \
	fi

	@$(eval EXTRA_FLAGS := )
	@$(eval EXTRA_FLAGS += PARENT=$(PARENT))
	@$(eval EXTRA_FLAGS += measure_name=$(MEASURE))
	@$(if $(strip $(TU)),$(eval EXTRA_FLAGS += Tu=$(TU)))

	@$(MAKE) variant-generic \
		PHASE=$(PHASE2) \
		VARIANTS_DIR=$(VARIANTS_DIR2) \
		VARIANT=$(VARIANT) \
		EXTRA_FLAGS="$(EXTRA_FLAGS)"

script2:
	$(MAKE) script-run-generic PHASE=$(PHASE2) SCRIPT_MODULE=$(SCRIPT2_MODULE) VARIANT=$(VARIANT)

check2: check-variant-format
	$(MAKE) check-results-generic \
		PHASE=$(PHASE2) \
		VARIANTS_DIR=$(VARIANTS_DIR2) \
		VARIANT=$(VARIANT)

register2: check-variant-format
	$(MAKE) register-generic \
		PHASE=$(PHASE2) \
		VARIANTS_DIR=$(VARIANTS_DIR2) \
		DVC_EXTS="parquet" \
		VARIANT=$(VARIANT)

remove2: check-variant-format
	$(MAKE) remove-generic PHASE=$(PHASE2) VARIANTS_DIR=$(VARIANTS_DIR2) VARIANT=$(VARIANT)

remove2-all:
	$(MAKE) remove-phase-all PHASE=$(PHASE2) VARIANTS_DIR=$(VARIANTS_DIR2)

help2:
	@echo "==============================================="
	@echo " 02 — BUILD TIME SERIES DATASET"
	@echo "==============================================="
	@echo ""
	@echo " Create:"
	@echo "   make variant2 VARIANT=v201 PARENT=v001 \\"
	@echo "       MEASURE=Battery_Active_Power"
	@echo ""
	@echo " Execution:"
	@echo "   make script2 VARIANT=v201"
	@echo ""
	@echo " Checking:"
	@echo "   make check2 VARIANT=v201"
	@echo ""
	@echo " Register:"
	@echo "   make register2 VARIANT=v201"
	@echo ""
	@echo " Remove: (only if no children variants)"
	@echo "   make remove2 VARIANT=v201"
	@echo ""
	@echo "==============================================="


PHASE3 = f03_windows
SCRIPT3_MODULE = scripts.phases.f03_windows
VARIANTS_DIR3 = executions/$(PHASE3)
############################################
# Usage:
#   make variant3 VARIANT=v301 PARENT=v201 \
#        OW=600 LT=100 PW=100 \
#        STRATEGY=synchro \
#        NAN_MODE=discard \
#        [TU=10]
############################################

############################################
# PHASE 3 — WINDOWS
############################################

PHASE3         = f03_windows
SCRIPT3_MODULE = scripts.phases.f03_windows
VARIANTS_DIR3  = executions/$(PHASE3)

############################################
# Create variant
############################################

variant3: check-variant-format
	@test -n "$(PARENT)"   || (echo "[ERROR] You must specify PARENT=v2XX (parent F02 variant)"; exit 1)
	@test -n "$(OW)"       || (echo "[ERROR] You must specify OW=<int>"; exit 1)
	@test -n "$(LT)"       || (echo "[ERROR] You must specify LT=<int>"; exit 1)
	@test -n "$(PW)"       || (echo "[ERROR] You must specify PW=<int>"; exit 1)
	@test -n "$(STRATEGY)" || (echo "[ERROR] You must specify STRATEGY=synchro|asynOW"; exit 1)
	@test -n "$(NAN_MODE)" || (echo "[ERROR] You must specify NAN_MODE=keep|discard"; exit 1)

	@$(eval EXTRA_FLAGS := )
	@$(eval EXTRA_FLAGS += PARENT=$(PARENT))
	@$(eval EXTRA_FLAGS += OW=$(OW))
	@$(eval EXTRA_FLAGS += LT=$(LT))
	@$(eval EXTRA_FLAGS += PW=$(PW))
	@$(eval EXTRA_FLAGS += window_strategy=$(STRATEGY))
	@$(eval EXTRA_FLAGS += nan_mode=$(NAN_MODE))
	@$(if $(strip $(TU)),$(eval EXTRA_FLAGS += Tu=$(TU)))

	@$(MAKE) variant-generic \
		PHASE=$(PHASE3) \
		VARIANTS_DIR=$(VARIANTS_DIR3) \
		VARIANT=$(VARIANT) \
		EXTRA_FLAGS="$(EXTRA_FLAGS)"

############################################
# Execute
############################################

script3:
	$(MAKE) script-run-generic \
		PHASE=$(PHASE3) \
		SCRIPT_MODULE=$(SCRIPT3_MODULE) \
		VARIANT=$(VARIANT)

############################################
# Check results
############################################

check3: check-variant-format
	$(MAKE) check-results-generic \
		PHASE=$(PHASE3) \
		VARIANTS_DIR=$(VARIANTS_DIR3) \
		VARIANT=$(VARIANT)

############################################
# Register
############################################

register3: check-variant-format
	$(MAKE) register-generic \
		PHASE=$(PHASE3) \
		VARIANTS_DIR=$(VARIANTS_DIR3) \
		DVC_EXTS="parquet" \
		VARIANT=$(VARIANT)

############################################
# Remove
############################################

remove3: check-variant-format
	$(MAKE) remove-generic \
		PHASE=$(PHASE3) \
		VARIANTS_DIR=$(VARIANTS_DIR3) \
		VARIANT=$(VARIANT)

remove3-all:
	$(MAKE) remove-phase-all \
		PHASE=$(PHASE3) \
		VARIANTS_DIR=$(VARIANTS_DIR3)

help3:
	@echo "==============================================="
	@echo " 03 — BUILD WINDOWS DATASET"
	@echo "==============================================="
	@echo ""
	@echo " Create:"
	@echo "   make variant3 VARIANT=v301 PARENT=v201 \\"
	@echo "       OW=600 LT=100 PW=100 \\"
	@echo "       STRATEGY=synchro \\"
	@echo "       NAN_MODE=discard"
	@echo ""
	@echo " Execution:"
	@echo "   make script3 VARIANT=v301"
	@echo ""
	@echo " Checking:"
	@echo "   make check3 VARIANT=v301"
	@echo ""
	@echo " Register:"
	@echo "   make register3 VARIANT=v301"
	@echo ""
	@echo " Remove: (only if no children variants)"
	@echo "   make remove3 VARIANT=v301"
	@echo ""
	@echo "==============================================="


PHASE4 = f04_targets
SCRIPT4_MODULE = scripts.phases.f04_targets
VARIANTS_DIR4 = executions/$(PHASE4)

############################################
# Usage:
#   make variant4 VARIANT=v401 PARENT=v301 \
#        THRESHOLD=80 \
#        DIRECTION=high \
#        [NAME=battery_high]
############################################

############################################
# PHASE 4 — TARGETS
############################################

PHASE4         = f04_targets
SCRIPT4_MODULE = scripts.phases.f04_targets
VARIANTS_DIR4  = executions/$(PHASE4)

############################################
# Create variant
############################################

variant4: check-variant-format
	@test -n "$(PARENT)"   || (echo "[ERROR] You must specify PARENT=v3XX (parent F03 variant)"; exit 1)
	@if [ "$(EVENT_STRATEGY)" != "transitions" ]; then \
		test -n "$(THRESHOLD)" || (echo "[ERROR] You must specify THRESHOLD=<0..100>"; exit 1); \
		test -n "$(DIRECTION)" || (echo "[ERROR] You must specify DIRECTION=high|low"; exit 1); \
	fi

	@$(eval EXTRA_FLAGS := )
	@$(eval EXTRA_FLAGS += PARENT=$(PARENT))
	@$(if $(strip $(EVENT_STRATEGY)),$(eval EXTRA_FLAGS += event_strategy=$(EVENT_STRATEGY)))
	@$(if $(strip $(THRESHOLD)),$(eval EXTRA_FLAGS += threshold=$(THRESHOLD)))
	@$(if $(strip $(DIRECTION)),$(eval EXTRA_FLAGS += direction=$(DIRECTION)))
	@$(if $(strip $(NAME)),$(eval EXTRA_FLAGS += prediction_name=$(NAME)))

	@$(MAKE) variant-generic \
		PHASE=$(PHASE4) \
		VARIANTS_DIR=$(VARIANTS_DIR4) \
		VARIANT=$(VARIANT) \
		EXTRA_FLAGS="$(EXTRA_FLAGS)"

############################################
# Execute
############################################

script4:
	$(MAKE) script-run-generic \
		PHASE=$(PHASE4) \
		SCRIPT_MODULE=$(SCRIPT4_MODULE) \
		VARIANT=$(VARIANT)

############################################
# Check results
############################################

check4: check-variant-format
	$(MAKE) check-results-generic \
		PHASE=$(PHASE4) \
		VARIANTS_DIR=$(VARIANTS_DIR4) \
		VARIANT=$(VARIANT)

############################################
# Register
############################################

register4: check-variant-format
	$(MAKE) register-generic \
		PHASE=$(PHASE4) \
		VARIANTS_DIR=$(VARIANTS_DIR4) \
		DVC_EXTS="parquet" \
		VARIANT=$(VARIANT)

############################################
# Remove
############################################

remove4: check-variant-format
	$(MAKE) remove-generic \
		PHASE=$(PHASE4) \
		VARIANTS_DIR=$(VARIANTS_DIR4) \
		VARIANT=$(VARIANT)

remove4-all:
	$(MAKE) remove-phase-all \
		PHASE=$(PHASE4) \
		VARIANTS_DIR=$(VARIANTS_DIR4)

help4:
	@echo "==============================================="
	@echo " 04 — TARGET ENGINEERING"
	@echo "==============================================="
	@echo ""
	@echo " Create:"
	@echo "   make variant4 VARIANT=v401 PARENT=v301 \\"
	@echo "       THRESHOLD=80 DIRECTION=high \\"
	@echo "       NAME=battery_high"
	@echo "   make variant4 VARIANT=v401 PARENT=v301 \\"
	@echo "       EVENT_STRATEGY=transitions NAME=event_transition_0_to_1"
	@echo ""
	@echo " Execution:"
	@echo "   make script4 VARIANT=v401"
	@echo ""
	@echo " Checking:"
	@echo "   make check4 VARIANT=v401"
	@echo ""
	@echo " Register:"
	@echo "   make register4 VARIANT=v401"
	@echo ""
	@echo " Remove:"
	@echo "   make remove4 VARIANT=v401"
	@echo ""
	@echo "==============================================="

############################################
# FASE 05 — MODELING
############################################

PHASE5 = f05_modeling
SCRIPT5_MODULE = scripts.phases.f05_model
VARIANTS_DIR5 = executions/$(PHASE5)

# Docker único para F05/F06 (reproducible entre OS)
ifeq ($(F56_GPU),true)
  F56_DOCKER_IMAGE ?= mlops-f56-gpu:latest
  F56_DOCKERFILE ?= scripts/docker/Dockerfile.f56_gpu
  F56_DOCKER_RUN_ARGS ?= --gpus all
else
  F56_DOCKER_IMAGE ?= mlops4ofp-f56:py311-tf215
  F56_DOCKERFILE ?= scripts/docker/Dockerfile.f56
  F56_DOCKER_RUN_ARGS ?=
endif
F56_DOCKER_PLATFORM ?= linux/amd64

ensure-f56-docker-image:
	@docker image inspect $(F56_DOCKER_IMAGE) >/dev/null 2>&1 || \
	(	echo "[INFO] Building Docker image $(F56_DOCKER_IMAGE) for F05/F06"; \
		docker build --platform $(F56_DOCKER_PLATFORM) -f $(F56_DOCKERFILE) -t $(F56_DOCKER_IMAGE) . )

############################################
# Usage:
#
#   make variant5 VARIANT=v501 PARENT=v401 \
#        MODEL_FAMILY=dense_bow \
#        IMBALANCE_STRATEGY=none \
#        [IMBALANCE_MAX_MAJ=200000] \
#        [BATCH_SIZE=128] \
#        [EPOCHS=50] \
#        [LEARNING_RATE=0.0005] \
#        [EARLY_STOPPING_PATIENCE=10] \
#        [EMBEDDING_DIM=256] \
#        [HIDDEN_UNITS=256] \
#        [DROPOUT=0.3]
############################################

variant5: check-variant-format
	@test -n "$(PARENT)" || (echo "[ERROR] You must specify PARENT=v4XX (parent F04 variant)"; exit 1)
	@test -n "$(MODEL_FAMILY)" || (echo "[ERROR] You must specify MODEL_FAMILY"; exit 1)

	@$(eval EXTRA_FLAGS := )
	@$(eval EXTRA_FLAGS += PARENT=$(PARENT))
	@$(eval EXTRA_FLAGS += model_family=$(MODEL_FAMILY))

	# Optional schema-native dict overrides
	@$(if $(strip $(AUTOML)), \
		$(eval EXTRA_FLAGS += automl=$(AUTOML)))
	@$(if $(strip $(SEARCH_SPACE)), \
		$(eval EXTRA_FLAGS += search_space=$(SEARCH_SPACE)))
	@$(if $(strip $(TRAINING)), \
		$(eval EXTRA_FLAGS += training=$(TRAINING)))
	@$(if $(strip $(EVALUATION)), \
		$(eval EXTRA_FLAGS += evaluation=$(EVALUATION)))

	# Imbalance explícito por variables separadas (evita dict JSON en CLI)
	@$(eval EXTRA_FLAGS += imbalance_strategy=$(if $(strip $(IMBALANCE_STRATEGY)),$(IMBALANCE_STRATEGY),none))
	@$(if $(strip $(IMBALANCE_MAX_MAJ)), \
		$(eval EXTRA_FLAGS += imbalance_max_majority_samples=$(IMBALANCE_MAX_MAJ)))
	
	# Deduplicación opcional (por defecto: none)
	@$(eval EXTRA_FLAGS += deduplication_mode=$(if $(strip $(DEDUP_MODE)),$(DEDUP_MODE),none))

	# Seed opcional (por defecto: 42)
	@$(eval EXTRA_FLAGS += seed=$(if $(strip $(SEED)),$(SEED),42))

	# Optional training hyperparameters (schema defaults si no se pasan)
	@$(if $(strip $(BATCH_SIZE)), \
		$(eval EXTRA_FLAGS += batch_size=$(BATCH_SIZE)))
	@$(if $(strip $(EPOCHS)), \
		$(eval EXTRA_FLAGS += epochs=$(EPOCHS)))
	@$(if $(strip $(LEARNING_RATE)), \
		$(eval EXTRA_FLAGS += learning_rate=$(LEARNING_RATE)))
	@$(if $(strip $(EARLY_STOPPING_PATIENCE)), \
		$(eval EXTRA_FLAGS += early_stopping_patience=$(EARLY_STOPPING_PATIENCE)))
	@$(if $(strip $(EMBEDDING_DIM)), \
		$(eval EXTRA_FLAGS += embedding_dim=$(EMBEDDING_DIM)))
	@$(if $(strip $(HIDDEN_UNITS)), \
		$(eval EXTRA_FLAGS += hidden_units=$(HIDDEN_UNITS)))
	@$(if $(strip $(DROPOUT)), \
		$(eval EXTRA_FLAGS += dropout=$(DROPOUT)))

	# Legacy flags: se mantienen para compatibilidad de CLI, pero el schema actual
	# puede rechazarlos si no están definidos como parámetros de fase.

	@$(MAKE) variant-generic \
		PHASE=$(PHASE5) \
		VARIANTS_DIR=$(VARIANTS_DIR5) \
		VARIANT=$(VARIANT) \
		EXTRA_FLAGS="$(EXTRA_FLAGS)"

script5: check-variant-format ensure-f56-docker-image
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE5) $(VARIANT))"; \
	$(UPDATE_VARIANT_VERIFIED) $(PHASE5) $$VARIANT_NORM none >/dev/null 2>&1 || true; \
	$(UPDATE_VARIANT_STATE) $(PHASE5) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_RUNNING) >/dev/null 2>&1 || true; \
	echo "==> Regenerating lineage dashboard"; \
	$(MAKE) --no-print-directory generate_lineage || true; \
	echo "==> Running F05 in Docker ($(F56_DOCKER_IMAGE)) for $$VARIANT_NORM"; \
	docker run --rm --platform $(F56_DOCKER_PLATFORM) \
		$(F56_DOCKER_RUN_ARGS) \
		$(DOCKER_HOST_USER_ARGS) \
		-v "$(DOCKER_HOST_PWD):$(DOCKER_WORKSPACE_PATH)" \
		-w $(DOCKER_WORKSPACE_PATH) \
		$(F56_DOCKER_IMAGE) \
		bash -lc "python -m $(SCRIPT5_MODULE) --variant $$VARIANT_NORM" || { \
			$(UPDATE_VARIANT_STATE) $(PHASE5) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_FAILED) >/dev/null 2>&1 || true; \
			echo "==> Regenerating lineage dashboard"; \
			$(MAKE) --no-print-directory generate_lineage || true; \
			exit 1; \
		}; \
	$(UPDATE_VARIANT_STATE) $(PHASE5) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_COMPLETED) >/dev/null 2>&1 || true; \
	echo "==> Regenerating lineage dashboard"; \
	$(MAKE) --no-print-directory generate_lineage || true


script5-a: check-variant-format
	$(MAKE) script-run-generic \
		PHASE=$(PHASE5) \
		SCRIPT_MODULE=$(SCRIPT5_MODULE) \
		VARIANT=$(VARIANT)


check5: check-variant-format
	$(MAKE) check-results-generic \
		PHASE=$(PHASE5) \
		VARIANTS_DIR=$(VARIANTS_DIR5) \
		VARIANT=$(VARIANT)

############################################
# PUBLICAR + REGISTRO MLFLOW
############################################

register5: check-variant-format
	@test -n "$(VARIANT)" || (echo "[ERROR] Usage: make register5 VARIANT=v5XX"; exit 1)
	@set -eu; \
	VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE5) $(VARIANT))"; \
	echo "==> Checking MLflow setup (from .mlops4ofp/setup.yaml)"; \
	MLFLOW_ENABLED=$$($(PYTHON) -c 'import pathlib,yaml; p=pathlib.Path(".mlops4ofp/setup.yaml"); cfg=(yaml.safe_load(p.read_text()) if p.exists() else {}); print("1" if isinstance(cfg,dict) and cfg.get("mlflow",{}).get("enabled",False) else "0")'); \
	if [ "$$MLFLOW_ENABLED" = "1" ]; then \
		echo "==> MLflow enabled: registering run for $(PHASE5):$$VARIANT_NORM"; \
		VAR_DIR="$(VARIANTS_DIR5)/$$VARIANT_NORM"; \
		OUTS="$$VAR_DIR/outputs.yaml"; \
		if [ ! -f "$$OUTS" ]; then \
			echo "[ERROR] outputs.yaml not found in $$VAR_DIR"; exit 1; \
		fi; \
		if ! command -v mlflow >/dev/null 2>&1; then \
			echo "[INFO] MLflow CLI not found in local environment — skipping MLflow registration"; \
		else \
			MLFLOW_URI="$$($(PYTHON) -c 'import pathlib,yaml; p=pathlib.Path(".mlops4ofp/setup.yaml"); cfg=yaml.safe_load(p.read_text()); print(cfg.get("mlflow",{}).get("tracking_uri",""))')"; \
			MLFLOW_URI="$$MLFLOW_URI" VARIANT="$$VARIANT_NORM" PHASE5="$(PHASE5)" $(PYTHON) -m scripts.core.mlflow_register; \
		fi; \
	else \
		echo "[INFO] MLflow disabled in setup - skipping MLflow registration"; \
	fi; \
	$(MAKE) register-generic \
		PHASE=$(PHASE5) \
		VARIANTS_DIR=$(VARIANTS_DIR5) \
		DVC_EXTS="h5 parquet" \
		VARIANT=$$VARIANT_NORM

############################################
# ELIMINAR VARIANTES
############################################

remove5: check-variant-format
	@echo "==> Removing MLflow run for $(PHASE5):$(VARIANT) if present"
	@MLFLOW_ENABLED=$$($(PYTHON) -c 'import pathlib,yaml; p=pathlib.Path(".mlops4ofp/setup.yaml"); cfg=(yaml.safe_load(p.read_text()) if p.exists() else {}); print("1" if isinstance(cfg,dict) and cfg.get("mlflow",{}).get("enabled",False) else "0")'; \
	if [ "$$MLFLOW_ENABLED" = "1" ]; then \
		OUTS="$(VARIANTS_DIR5)/$(VARIANT)/outputs.yaml"; \
		if [ -f "$$OUTS" ]; then \
			RUN_ID=$$($(PYTHON) -c 'import sys,yaml,pathlib; p=pathlib.Path(sys.argv[1]); data=yaml.safe_load(p.read_text()) or {}; print(((data.get("mlflow") or {}).get("run_id")) or "")' "$$OUTS"); \
			if [ -n "$$RUN_ID" ]; then \
				echo "[INFO] Deleting MLflow run $$RUN_ID"; \
				mlflow runs delete --run-id "$$RUN_ID" >/dev/null 2>&1 || echo "[WARN] Could not delete MLflow run $$RUN_ID"; \
			else \
				echo "[INFO] No MLflow run_id recorded in outputs.yaml"; \
			fi; \
		else \
			echo "[INFO] outputs.yaml not found; skipping MLflow cleanup"; \
		fi; \
	else \
		echo "[INFO] MLflow disabled in setup — skipping MLflow cleanup"; \
	fi

	$(MAKE) remove-generic PHASE=$(PHASE5) VARIANTS_DIR=$(VARIANTS_DIR5) VARIANT=$(VARIANT)

remove5-all:
	$(MAKE) remove-phase-all PHASE=$(PHASE5) VARIANTS_DIR=$(VARIANTS_DIR5)


help5:
	@echo "==============================================="
	@echo " 05 — MODELING"
	@echo "==============================================="
	@echo ""
	@echo " Create:"
	@echo "   make variant5 VARIANT=v501 PARENT=v401 \\"
	@echo "       MODEL_FAMILY=dense_bow \\"
	@echo "       IMBALANCE_STRATEGY=none"
	@echo "   DEDUP_MODE=none|auto|neg_only|all   (optional, default: none)"
	@echo "   SEED=42 (optional, default: 42)"
	@echo ""
	@echo " Optional overrides:"
	@echo "   BATCH_SIZE=128"
	@echo "   EPOCHS=50"
	@echo "   LEARNING_RATE=0.0005"
	@echo "   EARLY_STOPPING_PATIENCE=10"
	@echo "   EMBEDDING_DIM=256"
	@echo "   HIDDEN_UNITS=256"
	@echo "   DROPOUT=0.3"
	@echo "   AUTOML=true|false"
	@echo "   MAX_TRIALS=10"
	@echo "   SEARCH_SPACE='{\"lr\":[0.001,0.0005]}'"
	@echo "   EVAL_SPLIT='{train:0.7,val:0.15,test:0.15}'"
	@echo ""
	@echo " Execution:"
	@echo "   make script5 VARIANT=v501"
	@echo ""
	@echo " Checking:"
	@echo "   make check5 VARIANT=v501"
	@echo ""
	@echo " Register:"
	@echo "   make register5 VARIANT=v501"
	@echo ""
	@echo " Remove:"
	@echo "   make remove5 VARIANT=v501"
	@echo ""
	@echo "==============================================="


############################################
# FASE 06 — QUANTIZATION & EEDU
############################################

PHASE6         = f06_quant
SCRIPT6_MODULE = scripts.phases.f06_quant
VARIANTS_DIR6  = executions/$(PHASE6)

############################################
# Usage:
#
#   make variant6 VARIANT=v601 PARENT=v5XX \
#        [DEPLOY_TARGET=esp32] \
#        [DEPLOY_RUNTIME=esp-tflite-micro] \
#        [DEPLOY_VERSION=1.3.3] \
#        [REQUIRE_INT8=true] \
#        [MEMORY_LIMIT=327680] \
#        [QUANTIZATION='{"tflite_optimization":"INT8_FULL"}'] \
#        [THRESHOLDING='{"maximize_metric":"recall"}'] \
#        [EEDU='{"version":"1.0"}']
############################################


############################################
# Create variant
############################################

variant6: check-variant-format
	@test -n "$(PARENT)" || (echo "[ERROR] You must specify PARENT=v5XX (parent F05 variant)"; exit 1)

	@$(eval EXTRA_FLAGS := )
	@$(eval EXTRA_FLAGS += PARENT=$(PARENT))

	# -----------------------------
	# Deployment (simple CLI args)
	# -----------------------------

	@$(if $(strip $(DEPLOY_TARGET)), \
		$(eval EXTRA_FLAGS += deployment.target=$(DEPLOY_TARGET)))

	@test -n "$(DEPLOY_TARGET)" || echo "[INFO] Using default deployment target (esp32)"

	@$(if $(strip $(DEPLOY_RUNTIME)), \
		$(eval EXTRA_FLAGS += deployment.runtime=$(DEPLOY_RUNTIME)))

	@$(if $(strip $(DEPLOY_VERSION)), \
		$(eval EXTRA_FLAGS += deployment.runtime_version=$(DEPLOY_VERSION)))

	@$(if $(strip $(REQUIRE_INT8)), \
		$(eval EXTRA_FLAGS += deployment.require_int8=$(REQUIRE_INT8)))

	@$(if $(strip $(MEMORY_LIMIT)), \
		$(eval EXTRA_FLAGS += deployment.memory_limit_bytes=$(MEMORY_LIMIT)))

	# -----------------------------
	# Quantization / thresholding
	# -----------------------------

	@$(if $(strip $(QUANTIZATION)), \
		$(eval EXTRA_FLAGS += quantization=$(QUANTIZATION)))

	@$(if $(strip $(THRESHOLDING)), \
		$(eval EXTRA_FLAGS += thresholding=$(THRESHOLDING)))

	@$(if $(strip $(EEDU)), \
		$(eval EXTRA_FLAGS += eedu=$(EEDU)))

	@$(MAKE) variant-generic \
		PHASE=$(PHASE6) \
		VARIANTS_DIR=$(VARIANTS_DIR6) \
		VARIANT=$(VARIANT) \
		EXTRA_FLAGS="$(EXTRA_FLAGS)"

############################################
# Execute (Docker reproducible)
############################################

script6: check-variant-format ensure-f56-docker-image
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE6) $(VARIANT))"; \
	$(UPDATE_VARIANT_VERIFIED) $(PHASE6) $$VARIANT_NORM none >/dev/null 2>&1 || true; \
	$(UPDATE_VARIANT_STATE) $(PHASE6) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_RUNNING) >/dev/null 2>&1 || true; \
	echo "==> Regenerating lineage dashboard"; \
	$(MAKE) --no-print-directory generate_lineage || true; \
	echo "==> Running F06 in Docker ($(F56_DOCKER_IMAGE)) for $$VARIANT_NORM"; \
	docker run --rm --platform $(F56_DOCKER_PLATFORM) \
		$(F56_DOCKER_RUN_ARGS) \
		$(DOCKER_HOST_USER_ARGS) \
		-v "$(DOCKER_HOST_PWD):$(DOCKER_WORKSPACE_PATH)" \
		-w $(DOCKER_WORKSPACE_PATH) \
		$(F56_DOCKER_IMAGE) \
		bash -lc "python -m $(SCRIPT6_MODULE) --variant $$VARIANT_NORM" || { \
			$(UPDATE_VARIANT_STATE) $(PHASE6) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_FAILED) >/dev/null 2>&1 || true; \
			echo "==> Regenerating lineage dashboard"; \
			$(MAKE) --no-print-directory generate_lineage || true; \
			exit 1; \
		}; \
	$(UPDATE_VARIANT_STATE) $(PHASE6) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_COMPLETED) >/dev/null 2>&1 || true; \
	echo "==> Regenerating lineage dashboard"; \
	$(MAKE) --no-print-directory generate_lineage || true

script6-a: check-variant-format
	$(MAKE) script-run-generic \
		PHASE=$(PHASE6) \
		SCRIPT_MODULE=$(SCRIPT6_MODULE) \
		VARIANT=$(VARIANT)


############################################
# Check results (custom, stronger than generic)
############################################

check6: check-variant-format
	$(MAKE) check-results-generic \
		PHASE=$(PHASE6) \
		VARIANTS_DIR=$(VARIANTS_DIR6) \
		VARIANT=$(VARIANT)

############################################
# Register (conditional publish)
############################################

register6: check-variant-format
	@test -n "$(VARIANT)" || (echo "[ERROR] Usage: make register6 VARIANT=v6XX"; exit 1)

	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE6) $(VARIANT))"; \
	echo "==> Registering F06 variant $$VARIANT_NORM"

	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE6) $(VARIANT))"; \
	VAR_DIR="$(VARIANTS_DIR6)/$$VARIANT_NORM"; \
	EDGE_CAPABLE=$$($(PYTHON) -c "import os,yaml; d=yaml.safe_load(open(os.path.join('$$VAR_DIR','outputs.yaml'))); print('1' if d.get('exports',{}).get('edge_capable') else '0')"); \
	if [ "$$EDGE_CAPABLE" = "1" ]; then \
		echo "[INFO] edge_capable = true — registering full EEDU"; \
		$(MAKE) register-generic \
			PHASE=$(PHASE6) \
			VARIANTS_DIR=$(VARIANTS_DIR6) \
			DVC_EXTS="parquet h5 tflite" \
			GIT_ONLY_EXTS="yaml html cc" \
			VARIANT=$$VARIANT_NORM; \
	else \
		echo "[INFO] edge_capable = false — registering non-edge artifacts only"; \
		$(MAKE) register-generic \
			PHASE=$(PHASE6) \
			VARIANTS_DIR=$(VARIANTS_DIR6) \
			DVC_EXTS="parquet h5" \
			GIT_ONLY_EXTS="yaml html" \
			VARIANT=$$VARIANT_NORM; \
	fi

	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE6) $(VARIANT))"; \
	echo "[SUCCESS] Register6 completed for $$VARIANT_NORM"

############################################
# Remove
############################################

remove6: check-variant-format
	$(MAKE) remove-generic \
		PHASE=$(PHASE6) \
		VARIANTS_DIR=$(VARIANTS_DIR6) \
		VARIANT=$(VARIANT)

remove6-all:
	$(MAKE) remove-phase-all \
		PHASE=$(PHASE6) \
		VARIANTS_DIR=$(VARIANTS_DIR6)


help6:
	@echo "==============================================="
	@echo " 06 — QUANTIZATION & EEDU"
	@echo "==============================================="
	@echo ""
	@echo " Create:"
	@echo "   make variant6 VARIANT=v601 PARENT=v5XX \\"
	@echo "       [QUANTIZATION='{\"tflite_optimization\":\"INT8_FULL\",\"target_hw\":\"esp32\"}'] \\"
	@echo "       [THRESHOLDING='{\"strategy\":\"recalibrate_on_quantized\",\"maximize_metric\":\"recall\"}'] \\"
	@echo "       [EEDU='{\"version\":\"1.0\",\"layout\":\"default\"}']"
	@echo " Deployment:"
	@echo "   DEPLOY_TARGET=esp32"
	@echo "   DEPLOY_RUNTIME=esp-tflite-micro"
	@echo "   DEPLOY_VERSION=1.3.3"
	@echo "   REQUIRE_INT8=true"
	@echo "   MEMORY_LIMIT=327680"
	@echo ""
	@echo " Execution:"
	@echo "   make script6 VARIANT=v601"
	@echo ""
	@echo " Checking:"
	@echo "   make check6 VARIANT=v601"
	@echo ""
	@echo " Register:"
	@echo "   make register6 VARIANT=v601"
	@echo ""
	@echo " Remove:"
	@echo "   make remove6 VARIANT=v601"
	@echo ""
	@echo "==============================================="


############################################
# FASE 07 — MODEL VALIDATION (EDGE)
############################################

############################################
# Usage:
#
#   make variant7 VARIANT=v701 PARENT=v6XX \
#        PLATFORM=esp32 \
#        MTI_MS=... \
#        [ITMAX=...]
#		 [TIME_SCALE=0.01] \
#        [MAX_ROWS=200]
#        [MAX_LINES=1000]
#
#   make script7-prepare-build VARIANT=v701
#   make script7-build-only   VARIANT=v701
#   make script7-flash-run    VARIANT=v701 PORT=/dev/ttyUSB0 [BAUD=115200] [DRAIN_SECONDS=..]
#   make script7-post         VARIANT=v701
#
#   make script7 VARIANT=v701 PORT=/dev/ttyUSB0
############################################

############################################
# PHASE 7 — EDGE VALIDATION (HIL)
############################################

PHASE7         = f07_modval
SCRIPT7_PREP   = scripts.phases.f071_preparebuild
SCRIPT7_RUN    = scripts.phases.f072_flashrun
SCRIPT7_POST   = scripts.phases.f073_post
VARIANTS_DIR7  = executions/$(PHASE7)
# Virtual ESP32 runner (socat + QEMU)
ESP32_VIRT_DIR := $(abspath scripts/esp32_virtual)
VIRTUAL_PORT   ?= /tmp/ttyVUSB0
SOCAT_PORT     ?= 4000
ESP32_VIRT_DOCKER_IMAGE    ?= mlops4rtedge-esp32-virtual:latest
ESP32_VIRT_DOCKER_PLATFORM ?= linux/amd64

############################################
# Create variant
############################################

variant7: check-variant-format
	@test -n "$(PARENT)"   || (echo "[ERROR] You must specify PARENT=v6XX (parent F06 variant)"; exit 1)
	@test -n "$(PLATFORM)" || (echo "[ERROR] You must specify PLATFORM (e.g. esp32)"; exit 1)
	@test -n "$(MTI_MS)"   || (echo "[ERROR] You must specify MTI_MS (ms)"; exit 1)

	@echo "[INFO] PLATFORM=$(PLATFORM)"
	@echo "[INFO] MTI_MS=$(MTI_MS)"

	@$(eval EXTRA_FLAGS := )
	@$(eval EXTRA_FLAGS += PARENT=$(PARENT))
	@$(eval EXTRA_FLAGS += platform=$(PLATFORM))
	@$(eval EXTRA_FLAGS += MTI_MS=$(MTI_MS))

ifneq ($(strip $(VIRTUAL)),)
	@test "$(VIRTUAL)" = "true" -o "$(VIRTUAL)" = "false" || \
		(echo "[ERROR] VIRTUAL must be true or false"; exit 1)
	@$(eval EXTRA_FLAGS += virtual=$(VIRTUAL))
endif

ifneq ($(ITMAX),)
	@$(eval EXTRA_FLAGS += ITmax=$(ITMAX))
endif

ifneq ($(TIME_SCALE),)
	@$(eval EXTRA_FLAGS += time_scale_factor=$(TIME_SCALE))
else
	@echo "[INFO] TIME_SCALE not provided -> default=1.0"
endif

ifneq ($(MAX_ROWS),)
	@$(eval EXTRA_FLAGS += max_rows=$(MAX_ROWS))
endif

ifneq ($(MAX_LINES),)
	@$(eval EXTRA_FLAGS += serial_max_lines=$(MAX_LINES))
endif

ifneq ($(ESP_FLASH_MB),)
	@$(eval EXTRA_FLAGS += esp_flash_size_mb=$(ESP_FLASH_MB))
endif

	@$(MAKE) variant-generic \
		PHASE=$(PHASE7) \
		VARIANTS_DIR=$(VARIANTS_DIR7) \
		VARIANT=$(VARIANT) \
		EXTRA_FLAGS="$(EXTRA_FLAGS)"

############################################
# Subphases
############################################

script7-prepare-build:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE7) $(VARIANT))"; \
	$(PYTHON) -m $(SCRIPT7_PREP) --variant $$VARIANT_NORM

script7-build-only:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE7) $(VARIANT))"; \
	$(PYTHON) -m $(SCRIPT7_RUN) \
		--variant $$VARIANT_NORM \
		--build-only

script7-flash-run:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE7) $(VARIANT))"; \
	$(PYTHON) -m $(SCRIPT7_RUN) \
		--variant $$VARIANT_NORM \
		$(if $(PORT),--port $(PORT),) \
		$(if $(BAUD),--baud $(BAUD),) \
		$(if $(DRAIN_SECONDS),--drain-seconds $(DRAIN_SECONDS),)

script7-post:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE7) $(VARIANT))"; \
	$(PYTHON) -m $(SCRIPT7_POST) --variant $$VARIANT_NORM



############################################
# Virtual ESP32 — Infraestructura compartida
############################################
# Bare "python3" + $(abspath) = /repo/python3 (doesn't exist).
# If PYTHON has no slash it's a command name → resolve via which.
PYTHON_ABS = $(if $(findstring /,$(PYTHON)),$(abspath $(PYTHON)),$(shell which $(PYTHON)))

esp32-virt-verify:
	@$(MAKE) -C $(ESP32_VIRT_DIR) verify PYTHON="$(PYTHON_ABS)" || { \
		echo "[ERROR] Entorno virtual ESP32 no configurado. Ejecuta: make -C scripts/esp32_virtual install"; \
		exit 1; \
	}

esp32-virt-install:
	@$(MAKE) -C $(ESP32_VIRT_DIR) install PYTHON="$(PYTHON_ABS)"

esp32-virt-stop:
	@$(MAKE) -C $(ESP32_VIRT_DIR) stop PYTHON="$(PYTHON_ABS)"

esp32-virt-docker-build:
	@docker build --platform $(ESP32_VIRT_DOCKER_PLATFORM) \
		-f "$(ESP32_VIRT_DIR)/Dockerfile" \
		-t $(ESP32_VIRT_DOCKER_IMAGE) \
		"$(DOCKER_HOST_PWD)"

esp32-virt-docker-ensure:
	@docker image inspect $(ESP32_VIRT_DOCKER_IMAGE) >/dev/null 2>&1 || \
		$(MAKE) --no-print-directory esp32-virt-docker-build

esp32-virt-docker-run: esp32-virt-docker-ensure
	@[ -n "$(VARIANT)" ] || { echo "[ERROR] VARIANT requerido."; exit 1; }
	@EXTRA_MAKE_ARGS=""; \
	if [ -n "$(BAUD)" ]; then EXTRA_MAKE_ARGS="$$EXTRA_MAKE_ARGS BAUD=$(BAUD)"; fi; \
	if [ -n "$(DRAIN_SECONDS)" ]; then EXTRA_MAKE_ARGS="$$EXTRA_MAKE_ARGS DRAIN_SECONDS=$(DRAIN_SECONDS)"; fi; \
	docker run --rm -i \
		--platform $(ESP32_VIRT_DOCKER_PLATFORM) \
		-v "$(DOCKER_HOST_PWD):$(DOCKER_WORKSPACE_PATH)" \
		-w $(DOCKER_WORKSPACE_PATH) \
		--tmpfs /tmp:exec,size=512m \
		-e F07_IDF_RUNNER=native \
		$(ESP32_VIRT_DOCKER_IMAGE) \
		make script7-virtualESP32 VARIANT=$(VARIANT) \
			PYTHON=//opt/esp32-virt-venv/bin/python3 \
			PYTHON_LOCAL=//opt/esp32-virt-venv/bin/python3 \
			$$EXTRA_MAKE_ARGS

esp32-socat-start:
	@$(MAKE) -C $(ESP32_VIRT_DIR) start-socat \
		VIRTUAL_PORT=$(VIRTUAL_PORT) \
		SOCAT_PORT=$(SOCAT_PORT) \
		PYTHON="$(PYTHON_ABS)"

# Requiere: PHASE VARIANT
esp32-qemu-start:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE) $(VARIANT))"; \
	$(MAKE) -C $(ESP32_VIRT_DIR) start-qemu \
		VARIANT=$$VARIANT_NORM \
		SOCAT_PORT=$(SOCAT_PORT) \
		ESP_PROJECT_DIR="$(abspath executions/$(PHASE)/$$VARIANT_NORM/esp32_project)" \
		PYTHON="$(PYTHON_ABS)"

# Requiere: PHASE FLASH_MODULE VARIANT
esp32-flash-run-virtual:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE) $(VARIANT))"; \
	EXTRA_RUN_ARGS=""; \
	if [ -n "$(BAUD)" ]; then EXTRA_RUN_ARGS="$$EXTRA_RUN_ARGS --baud $(BAUD)"; fi; \
	if [ -n "$(DRAIN_SECONDS)" ]; then EXTRA_RUN_ARGS="$$EXTRA_RUN_ARGS --drain-seconds $(DRAIN_SECONDS)"; fi; \
	$(PYTHON) -m $(FLASH_MODULE) --variant $$VARIANT_NORM \
		--port $(VIRTUAL_PORT) \
		--skip-flash \
		$$EXTRA_RUN_ARGS

############################################
# Full execution (robust)
############################################
script7:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE7) $(VARIANT))"; \
	VIRTUALIZED="$$($(PYTHON) -c 'import sys, yaml; from pathlib import Path; phase, variant = sys.argv[1:3]; p=Path("executions")/phase/variant/"params.yaml"; d=(yaml.safe_load(p.read_text()) or {}) if p.exists() else {}; print("true" if d.get("parameters", {}).get("virtual", False) else "false")' "$(PHASE7)" "$$VARIANT_NORM")"; \
	EXTRA_MAKE_ARGS=""; \
	if [ -n "$(PORT)" ]; then EXTRA_MAKE_ARGS="$$EXTRA_MAKE_ARGS PORT=$(PORT)"; fi; \
	if [ -n "$(BAUD)" ]; then EXTRA_MAKE_ARGS="$$EXTRA_MAKE_ARGS BAUD=$(BAUD)"; fi; \
	if [ -n "$(DRAIN_SECONDS)" ]; then EXTRA_MAKE_ARGS="$$EXTRA_MAKE_ARGS DRAIN_SECONDS=$(DRAIN_SECONDS)"; fi; \
	if [ "$$VIRTUALIZED" = "true" ] && [ "$${F07_IDF_RUNNER:-}" != "native" ]; then \
		echo "[INFO] Execution mode: virtual"; \
		echo "[INFO] Virtual ESP32 selected -> running F07 inside Docker runner"; \
		$(MAKE) --no-print-directory esp32-virt-docker-run VARIANT=$$VARIANT_NORM $$EXTRA_MAKE_ARGS; \
	else \
		$(MAKE) --no-print-directory script7-native VARIANT=$$VARIANT_NORM $$EXTRA_MAKE_ARGS; \
	fi

script7-native:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE7) $(VARIANT))"; \
	LOCK_DIR="executions/$(PHASE7)/$$VARIANT_NORM/.script7.lock"; \
	if ! mkdir "$$LOCK_DIR" 2>/dev/null; then \
		echo "[ERROR] F07 $$VARIANT_NORM ya esta en ejecucion ($$LOCK_DIR)."; \
		echo "        Si no hay ningun proceso activo, elimina ese directorio de lock manualmente."; \
		exit 1; \
	fi; \
	trap 'rmdir "$$LOCK_DIR" 2>/dev/null || true' EXIT; \
	$(MAKE) --no-print-directory script7-mark-verified VARIANT=$$VARIANT_NORM VERIFIED=none; \
	$(MAKE) --no-print-directory script7-mark-state VARIANT=$$VARIANT_NORM STATE=$(LIFECYCLE_STATE_EXECUTION_RUNNING); \
	echo "==> Regenerating lineage dashboard"; \
	$(MAKE) --no-print-directory generate_lineage || true; \
	EDGE_CAPABLE="$$($(PYTHON) -c 'import yaml, sys; from pathlib import Path; v=sys.argv[1]; p=Path("executions")/"f07_modval"/v/"params.yaml"; d=(yaml.safe_load(p.read_text()) or {}) if p.exists() else {}; parent=d.get("parent"); o=(Path("executions")/"f06_quant"/str(parent)/"outputs.yaml") if parent else None; e=((yaml.safe_load(o.read_text()) or {}).get("exports", {})) if (o and o.exists()) else {}; print("true" if bool(e.get("edge_capable", False)) else "false")' "$$VARIANT_NORM")"; \
	if [ "$$EDGE_CAPABLE" = "false" ]; then \
		echo "[INFO] Parent not edge_capable -> running post only"; \
		$(MAKE) --no-print-directory script7-native-post-only VARIANT=$$VARIANT_NORM; \
	else \
		EXTRA_MAKE_ARGS=""; \
		if [ -n "$(PORT)" ]; then EXTRA_MAKE_ARGS="$$EXTRA_MAKE_ARGS PORT=$(PORT)"; fi; \
		if [ -n "$(BAUD)" ]; then EXTRA_MAKE_ARGS="$$EXTRA_MAKE_ARGS BAUD=$(BAUD)"; fi; \
		if [ -n "$(DRAIN_SECONDS)" ]; then EXTRA_MAKE_ARGS="$$EXTRA_MAKE_ARGS DRAIN_SECONDS=$(DRAIN_SECONDS)"; fi; \
		$(MAKE) --no-print-directory script7-native-run VARIANT=$$VARIANT_NORM $$EXTRA_MAKE_ARGS; \
	fi

script7-mark-state:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE7) $(VARIANT))"; \
	$(UPDATE_VARIANT_STATE) $(PHASE7) $$VARIANT_NORM $(STATE) >/dev/null 2>&1 || true

script7-mark-verified:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE7) $(VARIANT))"; \
	$(UPDATE_VARIANT_VERIFIED) $(PHASE7) $$VARIANT_NORM $(VERIFIED) >/dev/null 2>&1 || true

script7-native-post-only:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE7) $(VARIANT))"; \
	$(PYTHON) -m $(SCRIPT7_POST) --variant $$VARIANT_NORM; rc=$$?; \
	if [ $$rc -ne 0 ]; then \
		$(MAKE) --no-print-directory script7-mark-state VARIANT=$$VARIANT_NORM STATE=$(LIFECYCLE_STATE_EXECUTION_FAILED); \
	else \
		$(MAKE) --no-print-directory script7-mark-state VARIANT=$$VARIANT_NORM STATE=$(LIFECYCLE_STATE_EXECUTION_COMPLETED); \
	fi; \
	echo "==> Regenerating lineage dashboard"; \
	$(MAKE) --no-print-directory generate_lineage || true; \
	exit $$rc

script7-native-run:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE7) $(VARIANT))"; \
	VIRTUALIZED="$$($(PYTHON) -c 'import sys, yaml; from pathlib import Path; phase, variant = sys.argv[1:3]; p=Path("executions")/phase/variant/"params.yaml"; d=(yaml.safe_load(p.read_text()) or {}) if p.exists() else {}; print("true" if d.get("parameters", {}).get("virtual", False) else "false")' "$(PHASE7)" "$$VARIANT_NORM")"; \
	if [ "$$VIRTUALIZED" = "true" ]; then \
		echo "[INFO] Execution mode: virtual"; \
		$(MAKE) --no-print-directory script7-virtualESP32 VARIANT=$$VARIANT_NORM; \
		exit $$?; \
	fi; \
	echo "[INFO] Execution mode: physical"; \
	$(PYTHON) -m $(SCRIPT7_PREP) --variant $$VARIANT_NORM || { $(MAKE) --no-print-directory script7-mark-state VARIANT=$$VARIANT_NORM STATE=$(LIFECYCLE_STATE_EXECUTION_FAILED); $(MAKE) --no-print-directory generate_lineage || true; exit 1; }; \
	EXTRA_RUN_ARGS=""; \
	if [ -n "$(PORT)" ]; then EXTRA_RUN_ARGS="$$EXTRA_RUN_ARGS --port $(PORT)"; fi; \
	if [ -n "$(BAUD)" ]; then EXTRA_RUN_ARGS="$$EXTRA_RUN_ARGS --baud $(BAUD)"; fi; \
	if [ -n "$(DRAIN_SECONDS)" ]; then EXTRA_RUN_ARGS="$$EXTRA_RUN_ARGS --drain-seconds $(DRAIN_SECONDS)"; fi; \
	set +e; $(PYTHON) -m $(SCRIPT7_RUN) --variant $$VARIANT_NORM $$EXTRA_RUN_ARGS; run_rc=$$?; set -e; \
	[ $$run_rc -ne 0 ] && echo "[INFO] flash-run returned $$run_rc -> continuing with post" || true; \
	set +e; $(PYTHON) -m $(SCRIPT7_POST) --variant $$VARIANT_NORM; post_rc=$$?; set -e; \
	if [ $$post_rc -ne 0 ]; then \
		$(MAKE) --no-print-directory script7-mark-state VARIANT=$$VARIANT_NORM STATE=$(LIFECYCLE_STATE_EXECUTION_FAILED); \
		$(MAKE) --no-print-directory generate_lineage || true; \
		exit $$post_rc; \
	fi; \
	if [ $$run_rc -ne 0 ]; then \
		$(MAKE) --no-print-directory script7-mark-state VARIANT=$$VARIANT_NORM STATE=$(LIFECYCLE_STATE_EXECUTION_FAILED); \
		$(MAKE) --no-print-directory generate_lineage || true; \
		exit $$run_rc; \
	fi; \
	$(MAKE) --no-print-directory script7-mark-state VARIANT=$$VARIANT_NORM STATE=$(LIFECYCLE_STATE_EXECUTION_COMPLETED); \
	echo "==> Regenerating lineage dashboard"; \
	$(MAKE) --no-print-directory generate_lineage || true

############################################
# Full execution — Virtual ESP32 (socat + QEMU)
############################################
script7-virtualESP32:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE7) $(VARIANT))"; \
	VIRTUALIZED="$$($(PYTHON) -c 'import sys, yaml; from pathlib import Path; phase, variant = sys.argv[1:3]; p=Path("executions")/phase/variant/"params.yaml"; d=(yaml.safe_load(p.read_text()) or {}) if p.exists() else {}; print("true" if d.get("parameters", {}).get("virtual", False) else "false")' "$(PHASE7)" "$$VARIANT_NORM")"; \
	[ "$$VIRTUALIZED" = "true" ] || { echo "[ERROR] $(PHASE7):$$VARIANT_NORM has virtual=false. Create it with VIRTUAL=true."; exit 1; }
	@$(MAKE) --no-print-directory esp32-virt-verify
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE7) $(VARIANT))"; \
	EXTRA_MAKE_ARGS=""; \
	if [ -n "$(BAUD)" ]; then EXTRA_MAKE_ARGS="$$EXTRA_MAKE_ARGS BAUD=$(BAUD)"; fi; \
	if [ -n "$(DRAIN_SECONDS)" ]; then EXTRA_MAKE_ARGS="$$EXTRA_MAKE_ARGS DRAIN_SECONDS=$(DRAIN_SECONDS)"; fi; \
	$(MAKE) --no-print-directory script7-prepare-build VARIANT=$$VARIANT_NORM || exit 1; \
	$(MAKE) --no-print-directory esp32-socat-start || exit 1; \
	test -e $(VIRTUAL_PORT) || { echo "[ERROR] No existe $(VIRTUAL_PORT). Revisa /tmp/esp32-virt/socat.log"; $(MAKE) -C $(ESP32_VIRT_DIR) stop || true; exit 1; }; \
	set +e; $(MAKE) --no-print-directory script7-build-only VARIANT=$$VARIANT_NORM; build_rc=$$?; set -e; \
	if [ $$build_rc -ne 0 ]; then \
		$(MAKE) --no-print-directory script7-post VARIANT=$$VARIANT_NORM || true; \
		$(MAKE) -C $(ESP32_VIRT_DIR) stop || true; \
		exit $$build_rc; \
	fi; \
	$(MAKE) --no-print-directory esp32-qemu-start PHASE=$(PHASE7) VARIANT=$$VARIANT_NORM || { $(MAKE) -C $(ESP32_VIRT_DIR) stop || true; exit 1; }; \
	set +e; $(MAKE) --no-print-directory esp32-flash-run-virtual PHASE=$(PHASE7) FLASH_MODULE=$(SCRIPT7_RUN) VARIANT=$$VARIANT_NORM $$EXTRA_MAKE_ARGS; rc=$$?; set -e; \
	[ $$rc -ne 0 ] && echo "[INFO] flash-run returned $$rc -> continuing with post" || true; \
	$(MAKE) --no-print-directory script7-post VARIANT=$$VARIANT_NORM || { $(MAKE) -C $(ESP32_VIRT_DIR) stop || true; exit 1; }; \
	$(MAKE) -C $(ESP32_VIRT_DIR) stop || true; \
	exit $$rc

############################################
# Check
############################################

check7: check-variant-format
	$(MAKE) check-results-generic \
		PHASE=$(PHASE7) \
		VARIANTS_DIR=$(VARIANTS_DIR7) \
		VARIANT=$(VARIANT)

############################################
# Register
############################################

register7: check-variant-format
	@test -n "$(VARIANT)" || (echo "[ERROR] Usage: make register7 VARIANT=v7XX"; exit 1)

	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE7) $(VARIANT))"; \
	ESP_DIR="$(VARIANTS_DIR7)/$$VARIANT_NORM/esp32_project"; \
	if [ -d "$$ESP_DIR/build_generated" ]; then \
		echo "==> DVC-tracking esp32_project/build_generated"; \
		$(DVC) add "$$ESP_DIR/build_generated" || true; \
	fi; \
	if [ -d "$$ESP_DIR/data" ]; then \
		echo "==> DVC-tracking esp32_project/data"; \
		$(DVC) add "$$ESP_DIR/data" || true; \
	fi

	$(MAKE) register-generic \
		PHASE=$(PHASE7) \
		VARIANTS_DIR=$(VARIANTS_DIR7) \
		DVC_EXTS="csv json" \
		GIT_ONLY_EXTS="yaml txt html" \
		VARIANT=$(VARIANT)

############################################
# Remove
############################################

remove7: check-variant-format
	$(MAKE) remove-generic \
		PHASE=$(PHASE7) \
		VARIANTS_DIR=$(VARIANTS_DIR7) \
		VARIANT=$(VARIANT)

remove7-all:
	$(MAKE) remove-phase-all \
		PHASE=$(PHASE7) \
		VARIANTS_DIR=$(VARIANTS_DIR7)


help7:
	@echo "==============================================="
	@echo " 07 — MODEL VALIDATION ON EDGE"
	@echo "==============================================="
	@echo ""
	@echo " Create:"
	@echo "   make variant7 VARIANT=v701 PARENT=v6XX PLATFORM=esp32 MTI_MS=100000"
	@echo "     (MTI_MS is mandatory and must be provided in milliseconds)"
	@echo ""
	@echo " Parameters for variant7:"
	@echo "   Required:"
	@echo "     PARENT=v6XX"
	@echo "     PLATFORM=<edge folder name>   (e.g. esp32, stm32, arduino)"
	@echo "     MTI_MS=<milliseconds>"
	@echo "   Optional:"
	@echo "     TIME_SCALE=<float>   (default: 0.01)"
	@echo "     ITMAX=<integer>      (default: MTI_MS)"
	@echo "     MAX_ROWS=<integer>   (default: full dataset in 07_input_dataset.csv)"
	@echo "     MAX_LINES=<integer>  (default: send all lines from 07_input_dataset.csv)"
	@echo "     VIRTUAL=true|false   (default: false; stored in params.yaml)"
	@echo ""
	@echo " Execution (step-by-step):"
	@echo "   make script7-prepare-build VARIANT=v701"
	@echo "   make script7-flash-run   VARIANT=v701"
	@echo "   make script7-post    VARIANT=v701"
	@echo ""
	@echo " Full execution:"
	@echo "   make script7 VARIANT=v701"
	@echo ""
	@echo " Full execution (virtual ESP32 — socat+QEMU, sin hardware):"
	@echo "   Create the variant with VIRTUAL=true, then run:"
	@echo "   make script7 VARIANT=v701                     # preferred: runs virtual ESP32 inside Docker"
	@echo "   make esp32-virt-docker-build                  # optional: prebuilds the Docker runner image"
	@echo "   Legacy/native helper commands:"
	@echo "   make esp32-virt-verify                        # comprueba que el entorno está listo"
	@echo "   make esp32-virt-install                       # instala socat+QEMU si faltan"
	@echo "   make script7-virtualESP32 VARIANT=v701        # alias que exige virtual=true"
	@echo "   make esp32-virt-stop                          # para socat+QEMU"
	@echo ""
	@echo " Checking:"
	@echo "   make check7 VARIANT=v701"
	@echo ""
	@echo " Register:"
	@echo "   make register7 VARIANT=v701"
	@echo ""
	@echo "==============================================="

############################################
# FASE 08 — SYSTEM VALIDATION (MULTI-MODEL EDGE)
############################################


############################################
# Usage:
#
#   make variant8 VARIANT=v801 PARENTS='[v701, v702, ...]' \
#        (también admite PARENTS=v701,v702,...) \
#        PLATFORM=esp32 \
#        MTI_MS=... \
#        [TIME_SCALE=0.01] \
#        [MAX_ROWS=200] \
#        [MEMORY_BUDGET_BYTES=...] \
#        [MAX_MODELS=...] \
#        [MIN_QUALITY_SCORE=...]
#
#   make script8-select-config VARIANT=v801
#   make script8-prepare-build VARIANT=v801
#   make script8-build-only    VARIANT=v801
#   make script8-flash-run     VARIANT=v801 PORT=/dev/ttyUSB0 [MODE=serial|memory] [BAUD=115200] [DRAIN_SECONDS=..]
#   make script8-post          VARIANT=v801
#
#   make script8 VARIANT=v801 PORT=/dev/ttyUSB0
############################################

############################################
# PHASE 8 — SYSTEM VALIDATION (MULTI-MODEL)
############################################

PHASE8        = f08_sysval
VARIANTS_DIR8 = executions/$(PHASE8)

############################################
# Create variant (multi-parent)
############################################

variant8: check-variant-format
	@test -n "$(PARENTS)"  || (echo "[ERROR] You must specify PARENTS"; exit 1)
	@test -n "$(PLATFORM)" || (echo "[ERROR] You must specify PLATFORM"; exit 1)
	@test -n "$(MTI_MS)"   || (echo "[ERROR] You must specify MTI_MS"; exit 1)

ifneq ($(strip $(VIRTUAL)),)
	@test "$(VIRTUAL)" = "true" -o "$(VIRTUAL)" = "false" || \
		(echo "[ERROR] VIRTUAL must be true or false"; exit 1)
endif

	@echo "[INFO] PARENTS=$(PARENTS)"
	@echo "[INFO] PLATFORM=$(PLATFORM)"
	@echo "[INFO] MTI_MS=$(MTI_MS)"
	@set -eu; \
	PARENTS_NORM="$$( $(PYTHON) -c 'import sys, yaml; from scripts.core.params_manager import normalize_variant_id_for_phase; phase=sys.argv[1]; raw=sys.argv[2].strip(); value=yaml.safe_load(raw) if raw else None; assert value is not None; value = [item.strip() for item in raw.split(",") if item.strip()] if isinstance(value, str) and "," in raw and not raw.startswith("[") else ([value] if isinstance(value, str) else value); assert isinstance(value, list); normalized=[normalize_variant_id_for_phase(str(item), phase, "PARENTS") for item in value]; print("[" + ", ".join(normalized) + "]")' "$(PHASE7)" "$(PARENTS)")"; \
	SELECTION_MODE_VAL="$(if $(strip $(SELECTION_MODE)),$(SELECTION_MODE),manual)"; \
	EXTRA_FLAGS="parent_variant=$$PARENTS_NORM platform=$(PLATFORM) MTI_MS=$(MTI_MS) selection_mode=$$SELECTION_MODE_VAL"; \
	$(if $(strip $(OBJECTIVE)),EXTRA_FLAGS="$$EXTRA_FLAGS objective=$(OBJECTIVE)"; ) \
	$(if $(strip $(TIME_SCALE)),EXTRA_FLAGS="$$EXTRA_FLAGS time_scale_factor=$(TIME_SCALE)"; ) \
	$(if $(strip $(MAX_ROWS)),EXTRA_FLAGS="$$EXTRA_FLAGS max_rows=$(MAX_ROWS)"; ) \
	$(if $(strip $(VIRTUAL)),EXTRA_FLAGS="$$EXTRA_FLAGS virtual=$(VIRTUAL)"; ) \
	$(if $(strip $(MEMORY_BUDGET_BYTES)),EXTRA_FLAGS="$$EXTRA_FLAGS memory_budget_bytes=$(MEMORY_BUDGET_BYTES)"; ) \
	$(if $(strip $(MAX_MODELS)),EXTRA_FLAGS="$$EXTRA_FLAGS max_models=$(MAX_MODELS)"; ) \
	$(if $(strip $(MIN_QUALITY_SCORE)),EXTRA_FLAGS="$$EXTRA_FLAGS min_quality_score=$(MIN_QUALITY_SCORE)"; ) \
	$(if $(strip $(MIN_PRECISION)),EXTRA_FLAGS="$$EXTRA_FLAGS min_precision=$(MIN_PRECISION)"; ) \
	$(if $(strip $(MIN_RECALL)),EXTRA_FLAGS="$$EXTRA_FLAGS min_recall=$(MIN_RECALL)"; ) \
	echo "[INFO] Normalized parents: $$PARENTS_NORM"; \
	$(MAKE) variant-generic \
		PHASE=$(PHASE8) \
		VARIANTS_DIR=$(VARIANTS_DIR8) \
		VARIANT=$(VARIANT) \
		EXTRA_FLAGS="$$EXTRA_FLAGS"

############################################
# Subphases
############################################

script8-select-config:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE8) $(VARIANT))"; \
	$(PYTHON) -m scripts.phases.f081_selectconfig --variant $$VARIANT_NORM

script8-prepare-build:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE8) $(VARIANT))"; \
	$(PYTHON) -m scripts.phases.f082_preparebuild --variant $$VARIANT_NORM

script8-build-only:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE8) $(VARIANT))"; \
	echo "[INFO] Build-only for $$VARIANT_NORM"; \
	@docker run --rm -i \
		-v "$(DOCKER_HOST_PWD)/executions/$(PHASE8)/$$VARIANT_NORM/esp32_project:$(DOCKER_PROJECT_PATH)" \
		-w $(DOCKER_PROJECT_PATH) \
		--entrypoint /bin/bash \
		mlops4ofp-idf:6.0 \
		-lc "source /opt/esp/idf/export.sh >/dev/null 2>&1 && idf.py build"

script8-flash-run:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE8) $(VARIANT))"; \
	$(PYTHON) -m scripts.phases.f083_flashrun \
		--variant $$VARIANT_NORM \
		$(if $(PORT),--port $(PORT),) \
		$(if $(MODE),--mode $(MODE),) \
		$(if $(BAUD),--baud $(BAUD),) \
		$(if $(DRAIN_SECONDS),--drain-seconds $(DRAIN_SECONDS),)

script8-post:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE8) $(VARIANT))"; \
	$(PYTHON) -m scripts.phases.f084_post --variant $$VARIANT_NORM

script8-virtualESP32:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE8) $(VARIANT))"; \
	VIRTUALIZED="$$($(PYTHON) -c 'import sys, yaml; from pathlib import Path; phase, variant = sys.argv[1:3]; p=Path("executions")/phase/variant/"params.yaml"; d=(yaml.safe_load(p.read_text()) or {}) if p.exists() else {}; print("true" if d.get("parameters", {}).get("virtual", False) else "false")' "$(PHASE8)" "$$VARIANT_NORM")"; \
	[ "$$VIRTUALIZED" = "true" ] || { echo "[ERROR] $(PHASE8):$$VARIANT_NORM has virtual=false. Create it with VIRTUAL=true."; exit 1; }
	@$(MAKE) --no-print-directory esp32-virt-verify
	@$(MAKE) --no-print-directory script8 VARIANT=$(VARIANT) \
		$(if $(MODE),MODE=$(MODE),) \
		$(if $(BAUD),BAUD=$(BAUD),) \
		$(if $(DRAIN_SECONDS),DRAIN_SECONDS=$(DRAIN_SECONDS),)

############################################
# Full execution
############################################

script8:
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE8) $(VARIANT))"; \
	$(UPDATE_VARIANT_VERIFIED) $(PHASE8) $$VARIANT_NORM none >/dev/null 2>&1 || true; \
	$(UPDATE_VARIANT_STATE) $(PHASE8) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_RUNNING) >/dev/null 2>&1 || true; \
	echo "==> Regenerating lineage dashboard"; \
	$(MAKE) --no-print-directory generate_lineage || true; \
	$(PYTHON) -m scripts.phases.f081_selectconfig --variant $$VARIANT_NORM || { $(UPDATE_VARIANT_STATE) $(PHASE8) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_FAILED) >/dev/null 2>&1 || true; echo "==> Regenerating lineage dashboard"; $(MAKE) --no-print-directory generate_lineage || true; exit 1; }; \
	CONFIG_EDGE_CAPABLE="$$($(PYTHON) -c 'import yaml, sys; from pathlib import Path; v=sys.argv[1]; p=Path("executions")/"f08_sysval"/v/"08_selected_configuration.yaml"; d=(yaml.safe_load(p.read_text()) or {}) if p.exists() else {}; print("true" if bool(d.get("configuration_edge_capable", False)) else "false")' "$$VARIANT_NORM")"; \
	if [ "$$CONFIG_EDGE_CAPABLE" = "false" ]; then \
		echo "[INFO] configuration not edge_capable -> post only"; \
		$(PYTHON) -m scripts.phases.f084_post --variant $$VARIANT_NORM || { $(UPDATE_VARIANT_STATE) $(PHASE8) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_FAILED) >/dev/null 2>&1 || true; echo "==> Regenerating lineage dashboard"; $(MAKE) --no-print-directory generate_lineage || true; exit 1; }; \
		$(UPDATE_VARIANT_STATE) $(PHASE8) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_COMPLETED) >/dev/null 2>&1 || true; \
		echo "==> Regenerating lineage dashboard"; \
		$(MAKE) --no-print-directory generate_lineage || true; \
	else \
		VIRTUALIZED="$$($(PYTHON) -c 'import sys, yaml; from pathlib import Path; phase, variant = sys.argv[1:3]; p=Path("executions")/phase/variant/"params.yaml"; d=(yaml.safe_load(p.read_text()) or {}) if p.exists() else {}; print("true" if d.get("parameters", {}).get("virtual", False) else "false")' "$(PHASE8)" "$$VARIANT_NORM")"; \
		echo "[INFO] Execution mode: $$([ "$$VIRTUALIZED" = "true" ] && echo virtual || echo physical)"; \
		$(PYTHON) -m scripts.phases.f082_preparebuild --variant $$VARIANT_NORM $$([ "$$VIRTUALIZED" = "true" ] && printf -- "--virtual") || { $(UPDATE_VARIANT_STATE) $(PHASE8) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_FAILED) >/dev/null 2>&1 || true; echo "==> Regenerating lineage dashboard"; $(MAKE) --no-print-directory generate_lineage || true; exit 1; }; \
		if [ "$$VIRTUALIZED" = "true" ]; then \
			$(MAKE) --no-print-directory esp32-socat-start || { $(UPDATE_VARIANT_STATE) $(PHASE8) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_FAILED) >/dev/null 2>&1 || true; $(MAKE) --no-print-directory generate_lineage || true; exit 1; }; \
			test -e $(VIRTUAL_PORT) || { echo "[ERROR] No existe $(VIRTUAL_PORT). Revisa /tmp/esp32-virt/socat.log"; $(UPDATE_VARIANT_STATE) $(PHASE8) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_FAILED) >/dev/null 2>&1 || true; $(MAKE) --no-print-directory generate_lineage || true; exit 1; }; \
			$(PYTHON) -m scripts.phases.f083_flashrun --variant $$VARIANT_NORM --build-only || { $(UPDATE_VARIANT_STATE) $(PHASE8) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_FAILED) >/dev/null 2>&1 || true; $(MAKE) --no-print-directory generate_lineage || true; $(MAKE) -C $(ESP32_VIRT_DIR) stop || true; exit 1; }; \
			$(MAKE) --no-print-directory esp32-qemu-start PHASE=$(PHASE8) VARIANT=$(VARIANT) || { $(UPDATE_VARIANT_STATE) $(PHASE8) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_FAILED) >/dev/null 2>&1 || true; $(MAKE) --no-print-directory generate_lineage || true; $(MAKE) -C $(ESP32_VIRT_DIR) stop || true; exit 1; }; \
			set +e; \
			$(MAKE) --no-print-directory esp32-flash-run-virtual PHASE=$(PHASE8) FLASH_MODULE=scripts.phases.f083_flashrun VARIANT=$(VARIANT) \
				$(if $(MODE),MODE=$(MODE),) \
				$(if $(BAUD),BAUD=$(BAUD),) \
				$(if $(DRAIN_SECONDS),DRAIN_SECONDS=$(DRAIN_SECONDS),); \
			rc=$$?; set -e; \
			[ $$rc -ne 0 ] && echo "[INFO] flash-run returned $$rc -> continuing with post" || true; \
			$(PYTHON) -m scripts.phases.f084_post --variant $$VARIANT_NORM || { $(UPDATE_VARIANT_STATE) $(PHASE8) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_FAILED) >/dev/null 2>&1 || true; $(MAKE) --no-print-directory generate_lineage || true; $(MAKE) -C $(ESP32_VIRT_DIR) stop || true; exit 1; }; \
			$(MAKE) -C $(ESP32_VIRT_DIR) stop || true; \
			if [ $$rc -ne 0 ]; then \
				$(UPDATE_VARIANT_STATE) $(PHASE8) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_FAILED) >/dev/null 2>&1 || true; \
				$(MAKE) --no-print-directory generate_lineage || true; \
				exit $$rc; \
			fi; \
		else \
			set +e; \
			$(PYTHON) -m scripts.phases.f083_flashrun --variant $$VARIANT_NORM \
				$(if $(PORT),--port $(PORT),) \
				$(if $(MODE),--mode $(MODE),) \
				$(if $(BAUD),--baud $(BAUD),) \
				$(if $(DRAIN_SECONDS),--drain-seconds $(DRAIN_SECONDS),); \
			rc=$$?; \
			[ $$rc -ne 0 ] && echo "[INFO] flash-run returned $$rc -> continuing" || true; \
			$(PYTHON) -m scripts.phases.f084_post --variant $$VARIANT_NORM || { $(UPDATE_VARIANT_STATE) $(PHASE8) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_FAILED) >/dev/null 2>&1 || true; echo "==> Regenerating lineage dashboard"; $(MAKE) --no-print-directory generate_lineage || true; exit 1; }; \
			if [ $$rc -ne 0 ]; then \
				$(UPDATE_VARIANT_STATE) $(PHASE8) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_FAILED) >/dev/null 2>&1 || true; \
				$(MAKE) --no-print-directory generate_lineage || true; \
				exit $$rc; \
			fi; \
		fi; \
		$(UPDATE_VARIANT_STATE) $(PHASE8) $$VARIANT_NORM $(LIFECYCLE_STATE_EXECUTION_COMPLETED) >/dev/null 2>&1 || true; \
		echo "==> Regenerating lineage dashboard"; \
		$(MAKE) --no-print-directory generate_lineage || true; \
	fi

############################################
# Check
############################################

check8: check-variant-format
	$(MAKE) check-results-generic \
		PHASE=$(PHASE8) \
		VARIANTS_DIR=$(VARIANTS_DIR8) \
		VARIANT=$(VARIANT)

############################################
# Register
############################################

register8: check-variant-format
	@test -n "$(VARIANT)" || (echo "[ERROR] Usage: make register8 VARIANT=v8XX"; exit 1)

	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE8) $(VARIANT))"; \
	$(MAKE) register-generic \
		PHASE=$(PHASE8) \
		VARIANTS_DIR=$(VARIANTS_DIR8) \
		DVC_EXTS="csv json" \
		GIT_ONLY_EXTS="yaml txt html" \
		VARIANT=$$VARIANT_NORM

############################################
# Remove
############################################

remove8: check-variant-format
	@VARIANT_NORM="$$($(NORMALIZE_VARIANT_FOR_PHASE) $(PHASE8) $(VARIANT))"; \
	$(MAKE) remove-generic \
		PHASE=$(PHASE8) \
		VARIANTS_DIR=$(VARIANTS_DIR8) \
		VARIANT=$$VARIANT_NORM

remove8-all:
	$(MAKE) remove-phase-all \
		PHASE=$(PHASE8) \
		VARIANTS_DIR=$(VARIANTS_DIR8)


help8:
	@echo ""
	@echo "====================== F08 — SYSTEM VALIDATION ======================"
	@echo ""
	@echo "Genera una variante F08 (multi-model edge configuration)"
	@echo ""
	@echo "USO BÁSICO:"
	@echo "  make variant8 VARIANT=v800 PARENTS=v700,v703 PLATFORM=esp32 MTI_MS=100"
	@echo ""
	@echo "PARÁMETROS OBLIGATORIOS:"
	@echo "  VARIANT=v8XX              Nombre de variante"
	@echo "  PARENTS=v7XX,...          Modelos candidatos (F07)"
	@echo "  PLATFORM=esp32            Plataforma objetivo"
	@echo "  MTI_MS=100                Tiempo máximo total (ms)"
	@echo ""
	@echo "SELECCIÓN:"
	@echo "  SELECTION_MODE=manual | auto_ilp     (default: manual)"
	@echo "  OBJECTIVE=max_global_recall | max_tp"
	@echo ""
	@echo "FILTROS (opcionales):"
	@echo "  MIN_PRECISION=0.01"
	@echo "  MIN_RECALL=0.8"
	@echo "  MIN_QUALITY_SCORE=0.01"
	@echo ""
	@echo "RESTRICCIONES:"
	@echo "  MEMORY_BUDGET_BYTES=300000"
	@echo "  MAX_MODELS=3"
	@echo ""
	@echo "OTROS:"
	@echo "  TIME_SCALE=0.01"
	@echo "  MAX_ROWS=1000"
	@echo "  VIRTUAL=true|false   (default: false; stored in params.yaml)"
	@echo ""
	@echo "====================== EJEMPLOS ======================"
	@echo ""
	@echo "1. Selección manual:"
	@echo "  make variant8 VARIANT=v800 PARENTS=v700,v703 PLATFORM=esp32 MTI_MS=100"
	@echo ""
	@echo "2. ILP optimizando recall:"
	@echo "  make variant8 VARIANT=v801 PARENTS=v700,v703 PLATFORM=esp32 MTI_MS=100 \\"
	@echo "      SELECTION_MODE=auto_ilp OBJECTIVE=max_global_recall"
	@echo ""
	@echo "3. ILP optimizando TP:"
	@echo "  make variant8 VARIANT=v802 PARENTS=v700,v703 PLATFORM=esp32 MTI_MS=100 \\"
	@echo "      SELECTION_MODE=auto_ilp OBJECTIVE=max_tp"
	@echo ""
	@echo "4. ILP con filtros:"
	@echo "  make variant8 VARIANT=v803 PARENTS=v700,v703 PLATFORM=esp32 MTI_MS=100 \\"
	@echo "      SELECTION_MODE=auto_ilp OBJECTIVE=max_tp MIN_PRECISION=0.01"
	@echo ""
	@echo "====================================================================="
	@echo "Generates an F08 variant (multi-model edge configuration)"
	@echo ""
	@echo "BASIC USAGE:"
	@echo "  make variant8 VARIANT=v800 PARENTS=v700,v703 PLATFORM=esp32 MTI_MS=100"
	@echo ""
	@echo "MANDATORY PARAMETERS:"
	@echo "  VARIANT=v8XX              Variant name"
	@echo "  PARENTS=v7XX,...          Candidate models (F07)"
	@echo "  PLATFORM=esp32            Target platform"
	@echo "  MTI_MS=100                Maximum total time (ms)"
	@echo ""
	@echo "SELECTION:"
	@echo "  SELECTION_MODE=manual | auto_ilp     (default: manual)"
	@echo "  OBJECTIVE=max_global_recall | max_tp"
	@echo ""
	@echo "FILTERS (optional):"
	@echo "  MIN_PRECISION=0.01"
	@echo "  MIN_RECALL=0.8"
	@echo "  MIN_QUALITY_SCORE=0.01"
	@echo ""
	@echo "RESTRICTIONS:"
	@echo "  MEMORY_BUDGET_BYTES=300000"
	@echo "  MAX_MODELS=3"
	@echo ""
	@echo "OTHERS:"
	@echo "  TIME_SCALE=0.01"
	@echo "  MAX_ROWS=1000"
	@echo "  VIRTUAL=true|false   (default: false; stored in params.yaml)"
	@echo ""
	@echo "====================== EXAMPLES ======================"
	@echo ""
	@echo "1. Manual selection:"
	@echo "  make variant8 VARIANT=v800 PARENTS=v700,v703 PLATFORM=esp32 MTI_MS=100"
	@echo ""
	@echo "2. ILP optimizing recall:"
	@echo "  make variant8 VARIANT=v801 PARENTS=v700,v703 PLATFORM=esp32 MTI_MS=100 \\"
	@echo "      SELECTION_MODE=auto_ilp OBJECTIVE=max_global_recall"
	@echo ""
	@echo "3. ILP optimizing TP:"
	@echo "  make variant8 VARIANT=v802 PARENTS=v700,v703 PLATFORM=esp32 MTI_MS=100 \\"
	@echo "      SELECTION_MODE=auto_ilp OBJECTIVE=max_tp"
	@echo ""
	@echo "4. ILP with filters:"
	@echo "  make variant8 VARIANT=v803 PARENTS=v700,v703 PLATFORM=esp32 MTI_MS=100 \\"
	@echo "      SELECTION_MODE=auto_ilp OBJECTIVE=max_tp MIN_PRECISION=0.01"
	@echo ""
	@echo "====================================================================="


help: help-setup help1 help2 help3 help4 help5 help6 help7 help8
	@echo "==============================================="

############################################
# DATA — add file to DVC and push
############################################

DATA_FILE ?=

dvc-add-datafile:
	@test -n "$(DATA_FILE)" || (echo "[ERROR] You must specify DATA_FILE=<path/to/file>"; exit 1)
	@echo "==> Adding $(DATA_FILE) to DVC"
	$(DVC) add $(DATA_FILE)
	@echo "==> Staging DVC pointer and .gitignore"
	@git add "$(DATA_FILE).dvc"
	@git add "$$(dirname "$(DATA_FILE)")/.gitignore" 2>/dev/null || true
	@git add .gitignore 2>/dev/null || true
	@echo "==> Committing"
	@git commit -m "dvc: add data file $(DATA_FILE)" || true
	@echo "==> Pushing .dvc pointer to git remote"
	@if [ -f ".mlops4ofp/setup.yaml" ]; then \
		PUBLISH_REMOTE="$$($(PYTHON_LOCAL) -c 'import yaml,pathlib; cfg=yaml.safe_load(pathlib.Path(".mlops4ofp/setup.yaml").read_text()); print(cfg.get("git",{}).get("publish_remote_name","origin"))')"; \
		PUBLISH_BRANCH="$$($(PYTHON_LOCAL) -c 'import yaml,pathlib; cfg=yaml.safe_load(pathlib.Path(".mlops4ofp/setup.yaml").read_text()); print(cfg.get("git",{}).get("branch","main"))')"; \
		git push "$$PUBLISH_REMOTE" "HEAD:$$PUBLISH_BRANCH" || true; \
	else \
		echo "[INFO] .mlops4ofp/setup.yaml not found — skipping git push"; \
	fi
	@echo "==> Pushing data to DVC remote"
	$(DVC) push -r storage || true

############################################
# SETUP-BRANCH — create branch + setup + push data
############################################
# make setup-branch SETUP_CFG=setup/remote3.yaml DATA_FILE=data/raw.csv

setup-branch:
	@test -n "$(SETUP_CFG)" || (echo "[ERROR] You must specify SETUP_CFG=<file.yaml>"; exit 1)
	@test -n "$(DATA_FILE)" || (echo "[ERROR] You must specify DATA_FILE=<path/to/file>"; exit 1)
	@set -eu; \
	BRANCH="$$($(PYTHON_LOCAL) -c 'import yaml; print(yaml.safe_load(open("$(SETUP_CFG)")).get("git",{}).get("branch","main"))')"; \
	echo "==> Creating/switching to branch: $$BRANCH"; \
	git checkout -b "$$BRANCH" 2>/dev/null || git checkout "$$BRANCH"; \
	$(MAKE) setup SETUP_CFG=$(SETUP_CFG); \
	$(MAKE) dvc-add-datafile DATA_FILE=$(DATA_FILE)

############################################
# TEARDOWN-BRANCH — purge DVC remote, delete branch, reset setup
############################################

teardown-branch:
	@test -f ".mlops4ofp/setup.yaml" || (echo "[ERROR] .mlops4ofp/setup.yaml not found — run 'make setup' first or already torn down"; exit 1)
	@set -eu; \
	BRANCH="$$($(PYTHON_LOCAL) -c 'import yaml; print(yaml.safe_load(open(".mlops4ofp/setup.yaml")).get("git",{}).get("branch","main"))')"; \
	PUBLISH_REMOTE="$$($(PYTHON_LOCAL) -c 'import yaml; print(yaml.safe_load(open(".mlops4ofp/setup.yaml")).get("git",{}).get("publish_remote_name","origin"))')"; \
	CURRENT_BRANCH="$$(git rev-parse --abbrev-ref HEAD)"; \
	if [ "$$CURRENT_BRANCH" != "$$BRANCH" ]; then \
		echo "[ERROR] You are on '$$CURRENT_BRANCH' but the setup branch is '$$BRANCH'."; \
		echo "        Switch to '$$BRANCH' before running teardown-branch."; \
		exit 1; \
	fi; \
	echo "==> [1/5] Removing DVC pointer(s) and cleaning local cache"; \
	if [ -n "$(DATA_FILE)" ]; then \
		if [ -f "$(DATA_FILE).dvc" ]; then \
			$(DVC) remove "$(DATA_FILE).dvc" && echo "[OK] Untracked $(DATA_FILE).dvc" || echo "[WARN] dvc remove failed"; \
		else \
			echo "[INFO] $(DATA_FILE).dvc not found — skipping dvc remove"; \
		fi; \
	else \
		DVC_FILES="$$(find . -maxdepth 3 -type f -name '*.dvc' ! -path './.dvc/*' 2>/dev/null)"; \
		if [ -n "$$DVC_FILES" ]; then \
			for f in $$DVC_FILES; do $(DVC) remove "$$f" || true; done; \
			echo "[OK] Untracked all .dvc pointer files"; \
		else \
			echo "[INFO] No .dvc pointer files found — skipping dvc remove"; \
		fi; \
	fi; \
	echo "==> [2/5] Purging local DVC cache"; \
	$(DVC) gc --force -w 2>&1 || echo "[WARN] dvc gc failed"; \
	echo "[INFO] NOTE: dvc gc --cloud is not supported for HTTP remotes (DagHub)."; \
	echo "[INFO]       To free remote storage, delete data manually at https://dagshub.com"; \
	echo "==> [3/5] Switching to main"; \
	git checkout main; \
	echo "==> [4/5] Deleting local branch '$$BRANCH'"; \
	git branch -D "$$BRANCH"; \
	echo "==> [5/5] Deleting remote branch '$$BRANCH' (if pushed)"; \
	git push "$$PUBLISH_REMOTE" --delete "$$BRANCH" 2>/dev/null || echo "[INFO] Remote branch '$$BRANCH' not found or already deleted — skipping"
	@echo "==> Cleaning setup artifacts"
	@$(MAKE) clean-setup
	@echo "[OK] Branch teardown complete."

.PHONY: \
	setup check-setup clean-setup setup-branch teardown-branch dvc-add-datafile \
	nb-run-generic script-run-generic \
	variant-generic check-variant-format \
	register-generic remove-generic check-results-generic export-generic \
	script1 script2 script3 script4 script5 script6 script7 script7-native script7-virtualESP32 script8 \
	script7-prepare-build script7-build-only script7-flash-run script7-post \
	esp32-virt-verify esp32-virt-install esp32-virt-stop \
	esp32-virt-docker-build esp32-virt-docker-ensure esp32-virt-docker-run \
	esp32-socat-start esp32-qemu-start esp32-flash-run-virtual \
	script8-virtualESP32 \
	variant1 variant2 variant3 variant4 variant5 variant6 variant7 variant8 \
	check1 check2 check3 check4 check5 check6 check7 check8 \
	register1 register2 register3 register4 register5 register6 register7 register8 \
	remove1 remove2 remove3 remove4 remove5 remove6 remove7 remove8 \
	help1 help2 help3 help4 help5 help6 help7 help8 \
	dvc-pull dvc-clean

############################################
# DVC pull artifacts for a variant
############################################
# Usage: make dvc-pull VARIANT=v5_0012                          # one variant
#        make dvc-pull VARIANT=v2_0001,v1_0001,v5_0012          # several
#        make dvc-pull VARIANT=v7                                # all phase-7 variants
#        make dvc-pull VARIANT='v*_2*'                           # wildcard across phases
dvc-pull:
	@test -n "$(VARIANT)" || (echo "[ERROR] Usage: make dvc-pull VARIANT=vY_NNNN[,vY,v*_2*,...]"; exit 1)
	@set -eu; \
	if [ ! -f .dvc/config.local ]; then \
		echo "[INFO] .dvc/config.local not found — configuring DVC credentials from .env"; \
		if [ ! -f .env ]; then \
			echo "[ERROR] .env file not found. Create it with DAGSHUB_USER and DAGSHUB_TOKEN"; exit 1; \
		fi; \
		DAGSHUB_USER=$$(grep -E '^DAGSHUB_USER=' .env | cut -d= -f2- | tr -d '"'"'"' '); \
		DAGSHUB_TOKEN=$$(grep -E '^DAGSHUB_TOKEN=' .env | cut -d= -f2- | tr -d '"'"'"' '); \
		if [ -z "$$DAGSHUB_USER" ] || [ -z "$$DAGSHUB_TOKEN" ]; then \
			echo "[ERROR] DAGSHUB_USER and/or DAGSHUB_TOKEN not found in .env"; exit 1; \
		fi; \
		$(DVC) remote modify storage --local auth basic; \
		$(DVC) remote modify storage --local user "$$DAGSHUB_USER"; \
		$(DVC) remote modify storage --local password "$$DAGSHUB_TOKEN"; \
		echo "[OK] DVC credentials configured"; \
	fi; \
	for V in $$(echo "$(VARIANT)" | tr ',' ' '); do \
		case "$$V" in v[0-9]) V="$${V}_*" ;; esac; \
		DPATTERN=$$(echo "$$V" | sed -n 's/^v\([0-9*?]\).*/\1/p'); \
		if [ -z "$$DPATTERN" ]; then \
			echo "[ERROR] Cannot parse $$V. Expected: vY_NNNN, vY, or wildcard (v*_2*)"; exit 1; \
		fi; \
		DIRS=$$(ls -d executions/f0$${DPATTERN}_*/$$V 2>/dev/null || true); \
		if [ -z "$$DIRS" ]; then \
			echo "[INFO] No variant directories matching $$V — skipping"; continue; \
		fi; \
		for VAR_DIR in $$DIRS; do \
			DVC_FILES=$$(find "$$VAR_DIR" -maxdepth 1 -name '*.dvc' 2>/dev/null); \
			if [ -z "$$DVC_FILES" ]; then \
				echo "[INFO] No .dvc files in $$VAR_DIR — skipping"; continue; \
			fi; \
			echo "==> Pulling DVC artifacts for $$VAR_DIR"; \
			$(DVC) pull $$VAR_DIR/*.dvc; \
			echo "[OK] DVC pull complete for $$VAR_DIR"; \
		done; \
	done

############################################
# DVC clean: remove pulled artifacts for a variant
############################################
# Usage: make dvc-clean VARIANT=v5_0012                         # one variant
#        make dvc-clean VARIANT=v2_0001,v5_0012                  # several
#        make dvc-clean VARIANT=v7                               # all phase-7 variants
#        make dvc-clean VARIANT='v*_2*'                          # wildcard across phases
dvc-clean:
	@test -n "$(VARIANT)" || (echo "[ERROR] Usage: make dvc-clean VARIANT=vY_NNNN[,vY,v*_2*,...]"; exit 1)
	@set -eu; \
	for V in $$(echo "$(VARIANT)" | tr ',' ' '); do \
		case "$$V" in v[0-9]) V="$${V}_*" ;; esac; \
		DPATTERN=$$(echo "$$V" | sed -n 's/^v\([0-9*?]\).*/\1/p'); \
		if [ -z "$$DPATTERN" ]; then \
			echo "[ERROR] Cannot parse $$V. Expected: vY_NNNN, vY, or wildcard (v*_2*)"; exit 1; \
		fi; \
		DIRS=$$(ls -d executions/f0$${DPATTERN}_*/$$V 2>/dev/null || true); \
		if [ -z "$$DIRS" ]; then \
			echo "[INFO] No variant directories matching $$V — skipping"; continue; \
		fi; \
		for VAR_DIR in $$DIRS; do \
			for dvc_file in $$VAR_DIR/*.dvc; do \
				[ -f "$$dvc_file" ] || continue; \
				DATA_FILE="$${dvc_file%.dvc}"; \
				if [ -e "$$DATA_FILE" ]; then \
					rm -rf "$$DATA_FILE"; \
					echo "[OK] Removed $$DATA_FILE"; \
				fi; \
			done; \
		done; \
	done

############################################
# Utils
############################################
generate_lineage:
	${PYTHON} scripts/core/variants_lineage/generate_lineage.py
