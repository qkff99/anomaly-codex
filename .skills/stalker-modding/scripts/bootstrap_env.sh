#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
usage:
  bootstrap_env.sh status [tool...]
  bootstrap_env.sh ensure <tool...>
  bootstrap_env.sh install-hints [tool...]

known tools:
  python
  rg
  luac
EOF
}

have_tool() {
  case "$1" in
    python)
      command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1
      ;;
    rg)
      command -v rg >/dev/null 2>&1
      ;;
    luac)
      command -v luac5.1 >/dev/null 2>&1 || command -v luac >/dev/null 2>&1 || command -v lua5.1 >/dev/null 2>&1 || command -v lua >/dev/null 2>&1
      ;;
    *)
      return 1
      ;;
  esac
}

need_sudo() {
  if [ "$(id -u)" -eq 0 ]; then
    return 1
  fi
  if command -v sudo >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

run_pkg() {
  if need_sudo; then
    sudo "$@"
  else
    "$@"
  fi
}

detect_package_manager() {
  for manager in apt-get dnf yum pacman zypper brew; do
    if command -v "$manager" >/dev/null 2>&1; then
      echo "$manager"
      return 0
    fi
  done
  return 1
}

install_with_manager() {
  local manager="$1"
  local tool="$2"

  case "$manager:$tool" in
    apt-get:python)
      run_pkg apt-get update
      run_pkg apt-get install -y python3
      ;;
    apt-get:rg)
      run_pkg apt-get update
      run_pkg apt-get install -y ripgrep
      ;;
    apt-get:luac)
      run_pkg apt-get update
      run_pkg apt-get install -y lua5.1
      ;;
    dnf:python|yum:python)
      run_pkg "$manager" install -y python3
      ;;
    dnf:rg|yum:rg)
      run_pkg "$manager" install -y ripgrep
      ;;
    dnf:luac|yum:luac)
      run_pkg "$manager" install -y lua
      echo "warning: installed generic lua package; verify luac reports Lua 5.1 for Anomaly work"
      ;;
    pacman:python)
      run_pkg pacman -Sy --noconfirm python
      ;;
    pacman:rg)
      run_pkg pacman -Sy --noconfirm ripgrep
      ;;
    pacman:luac)
      run_pkg pacman -Sy --noconfirm lua
      echo "warning: installed generic lua package; verify luac reports Lua 5.1 for Anomaly work"
      ;;
    zypper:python)
      run_pkg zypper --non-interactive install python3
      ;;
    zypper:rg)
      run_pkg zypper --non-interactive install ripgrep
      ;;
    zypper:luac)
      run_pkg zypper --non-interactive install lua
      echo "warning: installed generic lua package; verify luac reports Lua 5.1 for Anomaly work"
      ;;
    brew:python)
      brew install python
      ;;
    brew:rg)
      brew install ripgrep
      ;;
    brew:luac)
      brew install lua
      echo "warning: installed generic lua package; verify luac reports Lua 5.1 for Anomaly work"
      ;;
    *)
      echo "no install recipe for tool '$tool' with package manager '$manager'" >&2
      return 1
      ;;
  esac
}

print_hints() {
  local tool="${1:-python}"
  case "$tool" in
    python)
      cat <<'EOF'
python install hints:
- Debian/Ubuntu/WSL: sudo apt-get install python3
- Fedora/RHEL: sudo dnf install python3
- Arch: sudo pacman -S python
- openSUSE: sudo zypper install python3
- macOS/Homebrew: brew install python
EOF
      ;;
    rg)
      cat <<'EOF'
ripgrep install hints:
- Debian/Ubuntu/WSL: sudo apt-get install ripgrep
- Fedora/RHEL: sudo dnf install ripgrep
- Arch: sudo pacman -S ripgrep
- openSUSE: sudo zypper install ripgrep
- macOS/Homebrew: brew install ripgrep
EOF
      ;;
    luac)
      cat <<'EOF'
luac install hints:
- Debian/Ubuntu/WSL: sudo apt-get install lua5.1
- Fedora/RHEL: sudo dnf install lua
- Arch: sudo pacman -S lua
- openSUSE: sudo zypper install lua
- macOS/Homebrew: brew install lua

Prefer Lua 5.1 for Anomaly work. After install, verify `luac -v` or `luac5.1 -v`.
EOF
      ;;
    *)
      echo "unknown tool: $tool" >&2
      return 1
      ;;
  esac
}

status_tools() {
  local failed=0
  for tool in "$@"; do
    if have_tool "$tool"; then
      echo "$tool: ok"
    else
      echo "$tool: missing"
      failed=1
    fi
  done
  return "$failed"
}

ensure_tools() {
  local manager
  manager="$(detect_package_manager || true)"
  if [ -z "$manager" ]; then
    echo "no supported package manager detected" >&2
    for tool in "$@"; do
      print_hints "$tool"
    done
    return 1
  fi

  local failed=0
  for tool in "$@"; do
    if have_tool "$tool"; then
      echo "$tool: ok"
      continue
    fi
    echo "$tool: installing with $manager"
    if ! install_with_manager "$manager" "$tool"; then
      failed=1
      print_hints "$tool"
      continue
    fi
    if have_tool "$tool"; then
      echo "$tool: installed"
    else
      echo "$tool: install command completed but tool still not found in PATH" >&2
      failed=1
    fi
  done
  return "$failed"
}

main() {
  if [ "$#" -lt 1 ]; then
    usage
    exit 1
  fi

  local command="$1"
  shift
  if [ "$#" -eq 0 ]; then
    set -- python
  fi

  case "$command" in
    status)
      status_tools "$@"
      ;;
    ensure)
      ensure_tools "$@"
      ;;
    install-hints)
      local tool
      for tool in "$@"; do
        print_hints "$tool"
      done
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
