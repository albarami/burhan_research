# Burhān — Environment & Stack Specification (docs/04_ENVIRONMENT_AND_STACK.md)

**Scope:** Phase 1 — CB-SEM v1 Core Release
**Status:** For review
**Governed by:** `02_REQUIREMENTS.md` (NFR-100/400 series) and `03_ARCHITECTURE.md` (AD-02, AD-04, AD-07, §11).
**Principle:** this document defines *what* must be installed and *how* it is pinned; the lockfiles (`uv.lock`, `renv.lock`) are the sole source of truth for exact versions. Any statement here that conflicts with a lockfile is a defect.

---

## 1. Platform

- **Host:** Windows 11 workstation (Threadripper-class CPU, 256 GB RAM, discrete NVIDIA GPU).
- **Execution environment:** **WSL2 Ubuntu 24.04 LTS**. All Burhān code, data processing, and statistical computation run inside WSL. The Windows side participates only as an optional local LLM host (LM Studio).
- **Filesystem rule:** the engine repository and all study data live on the WSL ext4 filesystem (e.g., under `~/`), never under `/mnt/c/...` — Windows-mounted paths cost an order of magnitude in I/O and introduce permission-bit noise that breaks hash stability.
- **GPU:** not used by the statistical pipeline. Relevant only if a local model serves an LLM node (Windows-side LM Studio).

## 2. Directory Layout

```
~/dev/burhan/                     engine repository (git; GitHub remote)
~/research/burhan-studies/        studies root (engine-external, FR-1402)
  └── <study>/inputs|config|runs|outputs
~/.config/burhan/                 llm.yaml, defaults.yaml (machine-local config)
~/.local/share/burhan/            caches (crosswalk cache, prompt render cache)
```

Environment variables (set in `~/.bashrc` or via `direnv`):

```bash
export BURHAN_STUDIES_DIR="$HOME/research/burhan-studies"
export BURHAN_CONFIG_DIR="$HOME/.config/burhan"
export TZ=UTC LC_ALL=C.UTF-8 PYTHONHASHSEED=0
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1   # deterministic numerics
export BURHAN_MAX_WORKERS=16                                        # AD-07 parallel budget
```

Single-threaded BLAS is deliberate: multithreaded reductions are a classic source of last-decimal nondeterminism, and NFR-101 outranks raw speed. Stage-level parallelism (bootstrap workers with derived seeds) supplies the throughput instead.

## 3. Python Toolchain

- **Manager:** `uv` (Astral). Interpreter pinned in `.python-version` (**CPython 3.12.x**); dependencies pinned in `uv.lock`.
- **Required packages (exact versions owned by `uv.lock`):**
  - Core: `pydantic` v2, `typer` (CLI), `jinja2` (renderer), `pyyaml`, `jsonschema`
  - Data: `pandas`, `numpy`, `scipy`, `pyarrow` (feather/parquet handoff)
  - Verification stats: `semopy` (≥ 2.x), `statsmodels`, `pingouin`
  - Packaging: `python-docx`, `openpyxl`, `matplotlib` (figures)
  - LLM adapters: `anthropic`, `openai` (also used for any OpenAI-compatible local endpoint)
  - Dev: `pytest`, `pytest-cov`, `ruff`, `mypy`, `pre-commit`
- **Rule:** no package outside `uv.lock` may be imported; CI/`burhan doctor` asserts the environment hash against the manifest (NFR-102).

## 4. R Toolchain

- **R version:** ≥ 4.4 (exact version pinned at bootstrap and recorded in `renv.lock`; installed from the CRAN apt repository for Ubuntu 24.04).
- **Pinning:** `renv` with `workers/r/renv.lock` as the source of truth. Every worker asserts `renv::status()` clean at startup and aborts on drift (AD-02, NFR-102).
- **Required packages (exact versions owned by `renv.lock`):**
  - Estimation: `lavaan` (≥ 0.6-19), `semTools`, `simsem`
  - Diagnostics: `psych`, `MVN` (Mardia), `car` (VIF)
  - Missing data: `mice` (MI alternative; FIML is lavaan-native)
  - Interop: `jsonlite`; `arrow` (deferred until a contract requires parquet interop — researcher deferral, 2026-07-03)
- **System libraries (apt):** `build-essential gfortran libcurl4-openssl-dev libssl-dev libxml2-dev libblas-dev liblapack-dev libarrow-dev`.

## 5. LLM Provider Configuration (per node)

Machine-local file `~/.config/burhan/llm.yaml`; validated at startup; **startup fails if `lineage(node_a) == lineage(node_c)`** (FR-304, AD-04). Model *lineage* is declared per provider entry (`anthropic.claude`, `openai.gpt`, `alibaba.qwen`, …) so the check is explicit, not inferred.

```yaml
nodes:
  node_a:            # Contract extraction — lineage L1
    provider: anthropic
    model: <pinned Claude model string>
    lineage: anthropic.claude
    temperature: 0
    max_retries: 2
  node_c:            # Muḥāsaba reviewer — lineage L2 ≠ L1
    provider: openai
    model: <pinned GPT model string>
    lineage: openai.gpt
    temperature: 0
    max_retries: 2
  node_b:            # Narration — any lineage
    provider: anthropic
    model: <pinned Claude model string>
    lineage: anthropic.claude
    temperature: 0
providers:
  anthropic: { api_key_env: ANTHROPIC_API_KEY }
  openai:    { api_key_env: OPENAI_API_KEY }
  local_lmstudio:
    base_url: http://localhost:1234/v1     # see §5.2
    api_key_env: LMSTUDIO_API_KEY          # dummy accepted
```

**5.1 Default assignment.** Node A and Node B on the Claude lineage; Node C on the GPT lineage — mirroring the standing build protocol (Claude authors, Codex-lineage reviews). Model strings are pinned in `llm.yaml` and hashed into every run manifest with the prompt-template versions (AD-04).

**5.2 Local model option (LM Studio).** Any node may be pointed at the Windows-side LM Studio server (OpenAI-compatible). From WSL: with mirrored networking (`.wslconfig` → `networkingMode=mirrored`), `localhost` works directly; otherwise use the Windows host address from WSL (`ip route show default | awk '{print $3}'`). Declare `lineage: alibaba.qwen` (or as appropriate) so the A≠C check remains meaningful. Local serving is the fully-offline option for confidential study documents.

**5.3 Boundary reminder (enforced in code, restated here for operators):** provider choice never changes what a node may see. Raw respondent-level data is excluded from every prompt by the adapter allowlist regardless of whether the endpoint is cloud or localhost (NFR-401).

## 6. Secrets

API keys via environment variables only (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`), loaded from `~/.config/burhan/.env` (mode `600`) through `direnv` or shell profile. Never in the repository, never in `llm.yaml`, never in run manifests — manifests record model strings and hashes, not credentials.

## 7. Determinism Controls (operational summary)

| Control | Setting | Requirement |
|---|---|---|
| Master seed | per run, recorded in manifest; HKDF-derived per stage/worker | NFR-101 |
| BLAS/OMP threads | 1 (env vars, §2) | NFR-101 |
| Python hashing | `PYTHONHASHSEED=0` | NFR-101 |
| Locale / TZ | `C.UTF-8` / `UTC` | NFR-101 |
| Env integrity | `uv.lock` + `renv.lock` hashes asserted at startup and recorded | NFR-102 |
| Parallelism | derived-seed workers only where certification proves bit-stability; else serial | AD-07 |

Certified pinned statistical outputs (known-answer seeds for optimizer-based simulations) are recorded **per certified environment** — the reference workstation and the CI regression runner — because bit-reproducibility (NFR-101) holds within an environment, not across differently built BLAS/linear-algebra binaries; cross-environment agreement is governed by the certified tolerance regime (FR-902), never bitwise equality. Platform-keyed pins in certification tests are sanctioned accordingly.

## 8. Bootstrap Procedure (one-time)

```bash
# 1. System packages
sudo apt update && sudo apt install -y build-essential gfortran \
  libcurl4-openssl-dev libssl-dev libxml2-dev libblas-dev liblapack-dev \
  libxt-dev pandoc direnv git

# 2. R (CRAN repo for Ubuntu 24.04) + renv
sudo apt install -y --no-install-recommends software-properties-common dirmngr
wget -qO- https://cloud.r-project.org/bin/linux/ubuntu/marutter_pubkey.asc \
  | sudo tee /etc/apt/trusted.gpg.d/cran.asc
sudo add-apt-repository "deb https://cloud.r-project.org/bin/linux/ubuntu noble-cran40/"
sudo apt update && sudo apt install -y r-base r-base-dev

# 3. uv + repository
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone git@github.com:<owner>/burhan.git ~/dev/burhan && cd ~/dev/burhan
uv sync                                    # creates .venv from uv.lock
Rscript -e 'install.packages("renv"); renv::restore(project="workers/r")'

# 4. Machine config
mkdir -p ~/.config/burhan && cp config/llm.example.yaml ~/.config/burhan/llm.yaml
cp config/env.example ~/.config/burhan/.env && chmod 600 ~/.config/burhan/.env
mkdir -p ~/research/burhan-studies

# 5. Verify
uv run burhan doctor
```

## 9. `burhan doctor` (environment verification)

Extends the CLI surface defined in `03_ARCHITECTURE.md` §3 (carried into `08_BUILD_SPEC.md`). Asserts, and prints pass/fail per line: WSL/ext4 location of repo and studies dir · Python interpreter and `uv.lock` hash · R version and `renv::status()` clean · required system libraries · BLAS thread pinning and env vars (§2) · `llm.yaml` schema-valid, keys resolvable, **lineage(A) ≠ lineage(C)** · connectivity probe per configured provider (one trivial completion, no artifacts sent) · write access to `BURHAN_STUDIES_DIR` · git clean/commit hash. `doctor` green is a precondition recorded in every run manifest.

## 10. Backup & Retention

- **Engine:** git history + GitHub remote (code and docs only; no data).
- **Studies:** `runs/` archives are the reproducibility record — never auto-pruned; back up `~/research/burhan-studies` to encrypted offline/Windows-side storage on the operator's schedule. Raw respondent data never leaves the workstation as part of any Burhān process (NFR-401); off-machine backups are an operator decision outside the engine.

## 11. Reference Workstation Note

The pipeline is CPU/RAM-bound and comfortably inside this machine's envelope (NFR-501 sizing: N ≤ 2,000 × ≤ 150 items with 5,000 bootstrap resamples overnight; in practice, hours). `BURHAN_MAX_WORKERS=16` leaves headroom on a 24-core part for interactive use during runs. No CUDA dependency exists anywhere in the engine.
