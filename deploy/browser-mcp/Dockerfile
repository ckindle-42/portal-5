# Portal 5 Browser MCP — Obscura backend (TASK_BROWSER_OBSCURA_MIGRATION_V1).
#
# Replaces the mcr.microsoft.com/playwright base (Chromium + Node, ~1.5GB) with
# a single pinned Obscura Rust binary (no Node, no Chromium). The Portal wrapper
# (browser_mcp.py) drives `obscura mcp --http` per profile and `obscura fetch
# --dump markdown` one-shot for the web_fetch fallback.
#
# Obscura is pinned by commit for supply-chain safety — do NOT track a moving
# release. Bump OBSCURA_REF deliberately and re-run the Phase 0 smoke.
# `scripts/check_obscura_updates.py` (weekly launchd job
# com.portal5.obscura-update-check) reports pin drift + security advisories.

# ── Stage 1: build Obscura (render + stealth) at a pinned commit ──────────────
FROM rust:1.90-bookworm AS obscura-build
ARG OBSCURA_REF=14da23ddc432eaf8de6a14b44037626ce6fd9415
RUN apt-get update && apt-get install -y --no-install-recommends \
        git cmake clang libclang-dev llvm-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
RUN git clone https://github.com/h4ckf0r0day/obscura.git /src \
    && cd /src && git checkout "${OBSCURA_REF}" \
    && cargo build --release -p obscura-cli --bins --features render,stealth \
    && cp target/release/obscura /out-obscura \
    && cp target/release/obscura-worker /out-obscura-worker

# ── Stage 2: runtime — slim python + the Obscura binaries + the wrapper ───────
FROM python:3.11-slim
WORKDIR /app

# Runtime libs Obscura's render/stealth build links against (BoringSSL is static;
# these cover font/graphics rasterization for screenshots/PDF).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=obscura-build /out-obscura /usr/local/bin/obscura
COPY --from=obscura-build /out-obscura-worker /usr/local/bin/obscura-worker
RUN chmod +x /usr/local/bin/obscura /usr/local/bin/obscura-worker

# Wrapper deps (matches the fleet's MCP SDK pin).
RUN pip install --no-cache-dir httpx starlette uvicorn "mcp>=2.0.0,<3.0.0"

RUN mkdir -p /app /profiles /audit
COPY portal/modules/research/tools/browser_mcp.py /app/browser_mcp.py
COPY portal/__init__.py /app/portal/__init__.py
COPY portal/platform/ /app/portal/platform/
COPY config/ /app/config/
COPY config/ /config/

ENV OBSCURA_BIN=/usr/local/bin/obscura \
    BROWSER_STEALTH=true \
    BROWSER_MCP_PORT=8923

EXPOSE 8923

CMD ["python3", "/app/browser_mcp.py"]
