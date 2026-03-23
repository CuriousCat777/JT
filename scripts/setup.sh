#!/usr/bin/env bash
set -euo pipefail

# Guardian One — Setup Script
# Sets up the development environment for the Guardian One platform.

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# --- Helpers ---
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()    { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }

# --- Resolve project root (parent of scripts/) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo ""
echo -e "${BOLD}========================================${NC}"
echo -e "${BOLD}  Guardian One — Environment Setup${NC}"
echo -e "${BOLD}========================================${NC}"
echo ""

# ------------------------------------------------------------------
# 1. Check Python 3.10+
# ------------------------------------------------------------------
info "Checking Python version..."

PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)
        major=$("$candidate" -c 'import sys; print(sys.version_info.major)' 2>/dev/null || echo 0)
        minor=$("$candidate" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo 0)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    fail "Python 3.10+ is required but was not found. Please install it and try again."
fi
success "Found $PYTHON ($version)"

# ------------------------------------------------------------------
# 2. Create virtual environment
# ------------------------------------------------------------------
VENV_DIR="$PROJECT_ROOT/venv"

if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/activate" ]; then
    info "Virtual environment already exists at venv/"
else
    info "Creating virtual environment..."
    "$PYTHON" -m venv "$VENV_DIR"
    success "Virtual environment created at venv/"
fi

# Activate
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
success "Virtual environment activated ($(python --version))"

# ------------------------------------------------------------------
# 3. Install dependencies
# ------------------------------------------------------------------
REQUIREMENTS="$PROJECT_ROOT/requirements.txt"

if [ -f "$REQUIREMENTS" ]; then
    info "Installing dependencies from requirements.txt..."
    pip install --upgrade pip --quiet
    pip install -r "$REQUIREMENTS" --quiet
    success "Dependencies installed"
else
    warn "requirements.txt not found — skipping dependency install"
fi

# ------------------------------------------------------------------
# 4. Create required directories
# ------------------------------------------------------------------
DIRS=("data" "logs" "sessions" "config")
created_dirs=()

for dir in "${DIRS[@]}"; do
    target="$PROJECT_ROOT/$dir"
    if [ ! -d "$target" ]; then
        mkdir -p "$target"
        created_dirs+=("$dir/")
    fi
done

if [ ${#created_dirs[@]} -gt 0 ]; then
    success "Created directories: ${created_dirs[*]}"
else
    info "All required directories already exist"
fi

# ------------------------------------------------------------------
# 5. Create .env template if missing
# ------------------------------------------------------------------
ENV_FILE="$PROJECT_ROOT/.env"
ENV_CREATED=false

if [ ! -f "$ENV_FILE" ]; then
    info "Creating .env template..."
    cat > "$ENV_FILE" << 'ENVEOF'
# Guardian One — Environment Configuration
# Copy this to .env and fill in your values

# Master passphrase for Vault encryption (REQUIRED for production)
# GUARDIAN_MASTER_PASSPHRASE=your-secure-passphrase-here

# Notion (write-only workspace sync)
# NOTION_TOKEN=

# Google Calendar / Gmail (place google_credentials.json in config/)
# GOOGLE_CREDENTIALS_PATH=config/google_credentials.json

# Financial integrations
# PLAID_CLIENT_ID=
# PLAID_SECRET=
# ROCKET_MONEY_API_KEY=
# EMPOWER_API_KEY=

# DoorDash
# DOORDASH_DEVELOPER_ID=
# DOORDASH_KEY_ID=
# DOORDASH_SIGNING_SECRET=

# n8n workflow automation
# N8N_BASE_URL=
# N8N_API_KEY=

# AI Engine
# OLLAMA_BASE_URL=http://localhost:11434
# ANTHROPIC_API_KEY=

# Notifications
# SMTP_HOST=smtp.gmail.com
# SMTP_PORT=587
# SMTP_USER=
# SMTP_PASSWORD=
# NOTIFICATION_EMAIL=
# TWILIO_ACCOUNT_SID=
# TWILIO_AUTH_TOKEN=
# TWILIO_FROM_NUMBER=
# NOTIFICATION_PHONE=
ENVEOF
    ENV_CREATED=true
    success "Created .env template — edit it with your credentials"
else
    info ".env file already exists"
fi

# ------------------------------------------------------------------
# 6. Quick verification test
# ------------------------------------------------------------------
info "Running quick verification..."

VERIFY_OK=true
VERIFY_MSG=""

# Check core imports
if python -c "import guardian_one" 2>/dev/null; then
    VERIFY_MSG="guardian_one package importable"
else
    VERIFY_MSG="guardian_one package not importable (may need 'pip install -e .')"
    VERIFY_OK=false
fi

# Check if pytest is available and tests exist
TESTS_STATUS=""
if command -v pytest &>/dev/null && [ -d "$PROJECT_ROOT/tests" ]; then
    # Run a fast smoke test (collect only, no execution) to verify test discovery
    if pytest --collect-only --quiet "$PROJECT_ROOT/tests" &>/dev/null; then
        TESTS_STATUS="test suite discoverable"
    else
        TESTS_STATUS="test discovery had issues (run 'pytest tests/ -v' to investigate)"
    fi
else
    TESTS_STATUS="pytest or tests/ not found — skipping"
fi

if [ "$VERIFY_OK" = true ]; then
    success "Verification: $VERIFY_MSG"
else
    warn "Verification: $VERIFY_MSG"
fi
info "Tests: $TESTS_STATUS"

# ------------------------------------------------------------------
# 7. Summary
# ------------------------------------------------------------------
echo ""
echo -e "${BOLD}========================================${NC}"
echo -e "${BOLD}  Setup Summary${NC}"
echo -e "${BOLD}========================================${NC}"
echo ""
echo -e "  Project root:    ${BOLD}$PROJECT_ROOT${NC}"
echo -e "  Python:          ${BOLD}$(python --version)${NC}"
echo -e "  Virtual env:     ${BOLD}$VENV_DIR${NC}"
if [ -f "$REQUIREMENTS" ]; then
echo -e "  Dependencies:    ${GREEN}installed${NC}"
else
echo -e "  Dependencies:    ${YELLOW}requirements.txt not found${NC}"
fi
echo -e "  Directories:     ${GREEN}data/ logs/ sessions/ config/${NC}"
if [ "$ENV_CREATED" = true ]; then
echo -e "  .env:            ${YELLOW}template created — fill in your values${NC}"
else
echo -e "  .env:            ${GREEN}already exists${NC}"
fi
echo ""
echo -e "  ${BOLD}Next steps:${NC}"
echo -e "    1. Activate the venv:  ${BLUE}source venv/bin/activate${NC}"
echo -e "    2. Configure .env with your API keys"
echo -e "    3. Run tests:          ${BLUE}pytest tests/ -v${NC}"
echo -e "    4. Start Guardian One: ${BLUE}python main.py${NC}"
echo ""
