#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Parse flags ───────────────────────────────────────────────────────────────
PROD=false
for arg in "$@"; do
    case "$arg" in
        --prod) PROD=true ;;
    esac
done

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║     CodeRunner Agent — Full Stack Setup      ║"
if $PROD; then
echo "║              (production mode)               ║"
fi
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── 0. Prerequisites ──────────────────────────────────────────────────────────
command -v docker  >/dev/null || error "Docker not found."
command -v git     >/dev/null || error "Git not found."
command -v python3 >/dev/null || error "Python 3 not found."
docker info >/dev/null 2>&1   || error "Docker daemon not running. Start Docker Desktop."

# ── 1. .env ───────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
    cp .env.example .env
    if $PROD; then
        warn ".env created from template. Uncomment/edit the PRODUCTION block (domain + CHANGE_ME secrets) then re-run."
    else
        warn ".env created. Set OPENAI_API_KEY then re-run."
    fi
    exit 0
fi
if grep -q "OPENAI_API_KEY=sk-\.\.\." .env; then
    error "OPENAI_API_KEY is still the placeholder. Edit .env first."
fi
if $PROD && grep -q "CHANGE_ME" .env; then
    error "Production .env still contains CHANGE_ME placeholders. Set strong secrets first."
fi
info ".env OK"

# ── 2. Clone Moodle source ────────────────────────────────────────────────────
if [ ! -d moodle-src ]; then
    info "Cloning Moodle 4.5 (shallow, ~5 min)..."
    git clone --depth=1 -b MOODLE_405_STABLE \
        https://github.com/moodle/moodle.git moodle-src
else
    info "moodle-src already exists"
fi

# ── 3. Clone CodeRunner plugins ───────────────────────────────────────────────
mkdir -p plugins

if [ ! -d plugins/coderunner ]; then
    info "Cloning CodeRunner plugin..."
    git clone --depth=1 \
        https://github.com/trampgeek/moodle-qtype_coderunner.git \
        plugins/coderunner
else
    info "plugins/coderunner already exists"
fi

if [ ! -d plugins/qbehaviour ]; then
    info "Cloning CodeRunner behaviour plugin..."
    git clone --depth=1 \
        https://github.com/trampgeek/moodle-qbehaviour_adaptive_adapted_for_coderunner.git \
        plugins/qbehaviour
else
    info "plugins/qbehaviour already exists"
fi

# ── 4. Apply agent patch ──────────────────────────────────────────────────────
info "Applying CodeRunner Agent patch..."
python3 apply_patch.py

# ── 5. Start services ─────────────────────────────────────────────────────────
if $PROD; then
    info "Building images and starting all services (production)..."
else
    info "Building images and starting all services..."
fi
docker compose up -d --build

# ── 6. Done ───────────────────────────────────────────────────────────────────
echo ""
if $PROD; then
    WWWROOT=$(grep -oP 'MOODLE_WWWROOT=\K.*' .env 2>/dev/null || echo "https://your-domain/coderunner-agent")
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║  All services started (production)!                             ║"
    echo "║                                                                  ║"
    echo "║  Moodle is initializing — this takes about 3-5 minutes.         ║"
    echo "║  Watch progress: docker compose logs -f moodle                  ║"
    echo "║                                                                  ║"
    echo "║  Next steps:                                                     ║"
    echo "║  1. Add Apache proxy rules from deploy/apache-coderunner-agent  ║"
    echo "║  2. Reload Apache: sudo systemctl reload apache2                ║"
    echo "║  3. Visit ${WWWROOT}/admin"
    echo "║     and click 'Upgrade Moodle database now'                     ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
else
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║  All services started!                                           ║"
    echo "║                                                                  ║"
    echo "║  Moodle is initializing — this takes about 3-5 minutes.         ║"
    echo "║  Watch progress: docker compose logs -f moodle                  ║"
    echo "║                                                                  ║"
    echo "║  URLs:                                                           ║"
    echo "║    Moodle      →  http://localhost                               ║"
    echo "║    Agent API   →  http://localhost:8001                          ║"
    echo "║    Jobe        →  http://cra-jobe (Docker network only)          ║"
    echo "║                                                                  ║"
    echo "║  Moodle admin:  admin  /  Admin1234!                             ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "  After Moodle loads, go to:"
    echo "  http://localhost/admin  → click 'Upgrade Moodle database now'"
    echo "  (this installs CodeRunner plugin automatically)"
fi
echo ""
