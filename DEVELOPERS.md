# Developer Guide

This document is for contributors who maintain or extend the pipeline code in this repository.

The public repository is intentionally code-only. Generated executions, local DVC state, DVC cache, MLflow local state, and project-specific DVC references must not be versioned here.

## Repository Role

This repository contains the reusable pipeline engine:

- Makefile orchestration.
- Setup automation.
- Phase implementations.
- Validation and traceability logic.
- Test and audit scripts.
- Documentation.

It is not the place to store project execution history or binary artifacts.

## Design Principles

1. Keep the repository reusable across projects.
2. Keep generated artifacts local or in the project-specific DVC backend.
3. Keep project-specific Git publishing under the setup-driven project flow, not in this public codebase.
4. Preserve traceability between phase variants without storing local execution outputs in Git.

## High-Level Architecture

The pipeline is phase-based.

Core directories:

1. [scripts/core](scripts/core) contains shared logic such as parameter management, traceability, lineage generation, and schema handling.
2. [scripts/phases](scripts/phases) contains the executable logic for phases F01 to F08.
3. [setup](setup) contains environment and backend setup automation.
4. [test](test) contains audit scripts, integration-style flows, and reporting helpers.
5. [edge](edge) contains embedded templates and platform-specific assets.

Main phase modules:

1. F01: [scripts/phases/f01_explore.py](scripts/phases/f01_explore.py)
2. F02: [scripts/phases/f02_events.py](scripts/phases/f02_events.py)
3. F03: [scripts/phases/f03_windows.py](scripts/phases/f03_windows.py)
4. F04: [scripts/phases/f04_targets.py](scripts/phases/f04_targets.py)
5. F05: [scripts/phases/f05_model.py](scripts/phases/f05_model.py)
6. F06: [scripts/phases/f06_quant.py](scripts/phases/f06_quant.py) and [scripts/phases/f06_packaging.py](scripts/phases/f06_packaging.py)
7. F07: [scripts/phases/f071_preparebuild.py](scripts/phases/f071_preparebuild.py), [scripts/phases/f072_flashrun.py](scripts/phases/f072_flashrun.py), [scripts/phases/f073_post.py](scripts/phases/f073_post.py)
8. F08: [scripts/phases/f081_selectconfig.py](scripts/phases/f081_selectconfig.py), [scripts/phases/f082_preparebuild.py](scripts/phases/f082_preparebuild.py), [scripts/phases/f083_flashrun.py](scripts/phases/f083_flashrun.py), [scripts/phases/f084_post.py](scripts/phases/f084_post.py)

## Execution Model

The Makefile is the main entry point.

For each phase the usual pattern is:

1. `variantN` creates a new variant definition.
2. `scriptN` executes the phase.
3. `checkN` validates expected outputs.
4. `registerN` validates traceability and pushes large artifacts to DVC.
5. `removeN` and `removeN-all` clean variants safely.

The generic registration logic is centralized in [Makefile](Makefile). It now skips Git add, commit, and push when `git.mode` is not `custom`.

## Setup Model

Setup is driven by YAML files and [setup/setup.py](setup/setup.py).

Supported setup modes in the current codebase:

1. Local project mode via [setup/local.yaml](setup/local.yaml)
2. Remote project mode template via [setup/remote.yaml](setup/remote.yaml)

Current intended behavior:

1. This repository stores code only.
2. User project artifacts go to the DVC backend configured by setup.
3. User project execution outputs remain local to that project workspace unless the project explicitly publishes its own references.

## Repository Hygiene Rules

Do version in Git:

1. Source code.
2. Tests.
3. Documentation.
4. Configuration templates.
5. Schemas and reusable edge templates.

Do not version in Git:

1. [executions/](executions)
2. [.dvc/](.dvc)
3. [.dvc_storage/](.dvc_storage)
4. [mlruns/](mlruns)
5. Project-generated `.dvc` files under executions.
6. Temporary logs, firmware bundles, exported model binaries, and build outputs.

The ignore policy is enforced in [ .gitignore ](.gitignore).

## Local Development Workflow

### Environment setup

```bash
make setup SETUP_CFG=setup/local.yaml
make check-setup
```

### Discover available commands

```bash
make help
```

### Run targeted flows

Examples:

```bash
make variant1 VARIANT=v001 RAW=./data/raw.csv CLEANING=basic
make script1 VARIANT=v001
make check1 VARIANT=v001
```

```bash
make variant6 VARIANT=v601 PARENT=v501 DEPLOY_TARGET=esp32 REQUIRE_INT8=true
make script6 VARIANT=v601
make check6 VARIANT=v601
```

### Clean local state

```bash
make clean-setup
```

## Testing Strategy

Important test and audit entry points include:

1. [test/run-test.sh](test/run-test.sh)
2. [test/run-test2.sh](test/run-test2.sh)
3. [test/run-test-audit.sh](test/run-test-audit.sh)

Audit notes:

1. The audit script intentionally tampers with intermediate artifacts and source files to verify traceability rules.
2. It no longer assumes that execution outputs are tracked by Git.
3. It restores `outputs.yaml` from a temporary backup rather than using `git checkout` on generated files.

## Traceability And Variant Control

Variant creation and validation depend on shared core services:

1. [scripts/core/params_manager.py](scripts/core/params_manager.py)
2. [scripts/core/traceability.py](scripts/core/traceability.py)
3. [scripts/traceability_schema.yaml](scripts/traceability_schema.yaml)

If you change parameter contracts, parent resolution, or phase outputs, update the schema and validate downstream phases.

## DVC And Publishing Rules

The repository policy is strict:

1. Running a phase may still create local DVC references inside a project workspace.
2. This repository must not keep those references under version control.
3. `register-generic` only performs Git add, commit, and push when `git.mode=custom`.
4. In normal code-repository usage, `git.mode=none` keeps this repository free from project outputs.

## Working On Hardware Phases

For F07 and F08, keep in mind:

1. Docker is used in some embedded build flows.
2. Edge templates live under [edge/](edge).
3. Serial ports, permissions, platform naming, and runtime logs differ across operating systems.
4. These differences should stay operational and isolated; the pipeline design itself should remain platform-neutral.

In practice, the main OS-specific concerns are:

1. Serial device naming and permissions.
2. Docker path translation, especially on Windows shells.
3. Edge toolchain installation details.

## Documentation Expectations

When you change user-visible workflow behavior, update:

1. [README.md](README.md) for pipeline users.
2. [DEVELOPERS.md](DEVELOPERS.md) for maintainers.
3. Setup templates when backends or publishing expectations change.
4. Cross-platform operational notes in the main documentation when OS-specific behavior changes.

## Release And Contribution Checklist

Before publishing changes:

1. Confirm no generated outputs are staged.
2. Confirm no DVC cache or MLflow state is staged.
3. Run at least the relevant phase checks or audit scripts for the area you changed.
4. Review Makefile help text if CLI parameters changed.
5. Verify the public repository still reflects a code-only policy.
