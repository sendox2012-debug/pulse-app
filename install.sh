#!/usr/bin/env bash
# PULSE System Monitor - build & install helper for Arch Linux
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

PKGNAME="pulse-monitor"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"

info() { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()   { echo -e "${GREEN}[ OK ]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[FAIL]${NC} $*" >&2; }

banner() {
  echo -e "${CYAN}"
  echo "╔═══════════════════════════════════════════════════════════╗"
  echo "║           PULSE SYSTEM MONITOR - INSTALLER                ║"
  echo "║                      Arch Linux                           ║"
  echo "╚═══════════════════════════════════════════════════════════╝"
  echo -e "${NC}"
}

check_arch() {
  [[ -f /etc/arch-release ]] || { err "This installer supports Arch Linux only."; exit 1; }
  ok "Arch Linux detected"
}

check_not_root() {
  [[ $EUID -ne 0 ]] || { err "makepkg must not be run as root. Run as normal user."; exit 1; }
  ok "Running as normal user"
}

check_deps() {
  info "Checking dependencies..."
  local missing=()
  command -v makepkg >/dev/null 2>&1 || missing+=("base-devel")
  command -v python  >/dev/null 2>&1 || missing+=("python")
  python -c "import PIL" 2>/dev/null || missing+=("python-pillow")

  if [[ ${#missing[@]} -gt 0 ]]; then
    warn "Missing: ${missing[*]}"
    read -rp "Install them now? [Y/n] " reply
    if [[ ! $reply =~ ^[Nn]$ ]]; then
      sudo pacman -S --needed "${missing[@]}"
      ok "Dependencies installed"
    else
      err "Cannot continue without dependencies"; exit 1
    fi
  else
    ok "All dependencies satisfied"
  fi
}

check_files() {
  info "Checking source files..."
  local f
  for f in PKGBUILD pulse.py pulse.png pulse.desktop; do
    [[ -f "$SCRIPT_DIR/$f" ]] || { err "Missing file: $f"; exit 1; }
  done
  ok "All source files found"
}

clean_build() {
  info "Cleaning previous builds..."
  rm -rf "$BUILD_DIR" "$SCRIPT_DIR/pkg" "$SCRIPT_DIR/src"
  rm -f "$SCRIPT_DIR"/*.pkg.tar.*
  mkdir -p "$BUILD_DIR"
  ok "Build directory ready"
}

build_package() {
  info "Building package with makepkg..."
  cd "$BUILD_DIR"
  cp "$SCRIPT_DIR/PKGBUILD" "$SCRIPT_DIR/pulse.py" \
     "$SCRIPT_DIR/pulse.png" "$SCRIPT_DIR/pulse.desktop" .
  makepkg -sf --noconfirm
  ok "Package built"
}

install_package() {
  local -a pkgs=("$BUILD_DIR"/*.pkg.tar.*)
  [[ -e ${pkgs[0]} ]] || { err "No package file found in $BUILD_DIR"; exit 1; }
  local newest
  newest=$(ls -t "${pkgs[@]}" | head -n1)
  info "Installing: $(basename "$newest")"
  sudo pacman -U --noconfirm "$newest"
  ok "Package installed"
}

post_install() {
  info "Updating desktop & icon caches..."
  command -v update-desktop-database >/dev/null 2>&1 \
    && sudo update-desktop-database /usr/share/applications/ 2>/dev/null || true
  command -v gtk-update-icon-cache >/dev/null 2>&1 \
    && sudo gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true
  ok "Caches updated"
}

show_usage() {
  echo
  ok "Installation complete!"
  echo
  echo -e "${CYAN}Run:${NC}"
  echo "  • terminal : ${GREEN}pulse${NC}"
  echo "  • app menu : ${GREEN}PULSE System Monitor${NC}"
  echo
  echo -e "${CYAN}Manage:${NC}"
  echo "  • uninstall: ${YELLOW}sudo pacman -R pulse-monitor${NC}"
  echo "  • info     : ${YELLOW}pacman -Qi pulse-monitor${NC}"
  echo
  echo -e "${CYAN}Paths:${NC}"
  echo "  • binary   : /usr/bin/pulse"
  echo "  • icon     : /usr/share/icons/hicolor/256x256/apps/pulse.png"
  echo "  • data     : ~/.config/pulse/processes.json"
  echo
}

uninstall() {
  warn "Uninstalling $PKGNAME..."
  if pacman -Qi "$PKGNAME" >/dev/null 2>&1; then
    sudo pacman -R --noconfirm "$PKGNAME"
    ok "Package removed"
    read -rp "Also remove user data (~/.config/pulse)? [y/N] " reply
    [[ $reply =~ ^[Yy]$ ]] && rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/pulse" && info "User data removed"
  else
    warn "Package is not installed"
  fi
}

usage() {
  echo "Usage: $0 [OPTIONS]"
  echo "  (no options)   build and install pulse-monitor"
  echo "  -u, --uninstall  remove pulse-monitor"
  echo "  -h, --help       show this help"
}

main() {
  banner
  case "${1:-}" in
    -u|--uninstall) uninstall; exit 0 ;;
    -h|--help)      usage;     exit 0 ;;
    "")             ;;
    *) err "Unknown option: $1"; usage; exit 1 ;;
  esac

  check_arch
  check_not_root
  check_deps
  check_files
  clean_build
  build_package
  install_package
  post_install
  show_usage

  read -rp "Clean build files? [Y/n] " reply
  if [[ ! $reply =~ ^[Nn]$ ]]; then
    rm -rf "$BUILD_DIR"
    info "Build files cleaned"
  fi
}

main "$@"