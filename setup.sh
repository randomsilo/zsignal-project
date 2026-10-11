#!/bin/bash
# Checks this box's dependencies for running zsignal-web / zsignal-receiver
# via Docker (and for native CLI diagnostics alongside it, per SETUP.md).
#
#   ./setup.sh          report only
#   ./setup.sh --fix    also run the suggested commands, after confirming
#
# Safe to re-run any time -- every check is read-only until --fix is passed,
# and each fix command is itself idempotent.

set -u

FIX=0
if [ "${1:-}" = "--fix" ]; then
    FIX=1
fi

MISSING_PKGS=()
MISSING_GROUPS=()
NOTES=()
FAIL=0

ok()      { printf '[OK]      %s\n' "$1"; }
missing() { printf '[MISSING] %s\n' "$1"; FAIL=1; }

echo "== System =="
echo "arch:    $(uname -m)"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "os:      ${PRETTY_NAME:-unknown}"
fi
echo

echo "== Docker (runs zsignal-web / zsignal-receiver) =="
if command -v docker >/dev/null 2>&1; then
    ok "docker ($(docker --version))"
else
    missing "docker"
    MISSING_PKGS+=("docker.io")
fi
if docker compose version >/dev/null 2>&1; then
    ok "docker compose"
else
    missing "docker compose plugin"
    MISSING_PKGS+=("docker-compose-v2")
fi
echo

echo "== ALSA utils (host-side diagnostics/mixer tuning -- see SETUP.md) =="
for tool in aplay arecord amixer; do
    if command -v "$tool" >/dev/null 2>&1; then
        ok "$tool"
    else
        missing "$tool"
        MISSING_PKGS+=("alsa-utils")
    fi
done
echo

echo "== Python (native CLI diagnostics outside Docker) =="
if command -v python3 >/dev/null 2>&1; then
    ok "python3 ($(python3 --version 2>&1))"
else
    missing "python3"
    MISSING_PKGS+=("python3")
fi
if command -v pip3 >/dev/null 2>&1; then
    ok "pip3"
else
    missing "pip3"
    MISSING_PKGS+=("python3-pip")
fi
if python3 -c "import serial" >/dev/null 2>&1; then
    ok "pyserial"
else
    missing "pyserial (python3 -m pip install pyserial)"
    NOTES+=("pip3 install pyserial")
fi
echo

echo "== Group membership (log out and back in after any usermod) =="
for grp in docker dialout audio; do
    if groups "$USER" 2>/dev/null | grep -qw "$grp"; then
        ok "in '$grp' group"
    else
        missing "not in '$grp' group"
        MISSING_GROUPS+=("$grp")
    fi
done
echo

# De-dupe MISSING_PKGS while preserving order.
UNIQUE_PKGS=()
for p in "${MISSING_PKGS[@]:-}"; do
    [ -z "$p" ] && continue
    skip=0
    for seen in "${UNIQUE_PKGS[@]:-}"; do
        [ "$seen" = "$p" ] && skip=1 && break
    done
    [ "$skip" -eq 0 ] && UNIQUE_PKGS+=("$p")
done

if [ "$FAIL" -eq 0 ]; then
    echo "All checks passed."
    exit 0
fi

echo "== Suggested commands =="
APT_CMD=""
if [ "${#UNIQUE_PKGS[@]}" -gt 0 ]; then
    APT_CMD="sudo apt-get update && sudo apt-get install -y ${UNIQUE_PKGS[*]}"
    echo "$APT_CMD"
    if printf '%s\n' "${UNIQUE_PKGS[@]}" | grep -q '^docker'; then
        echo "  (if docker-compose-v2/docker.io are too old on your distro, use:"
        echo "   curl -fsSL https://get.docker.com | sh)"
    fi
fi
GROUP_CMDS=()
for grp in "${MISSING_GROUPS[@]:-}"; do
    [ -z "$grp" ] && continue
    cmd="sudo usermod -aG $grp \$USER"
    echo "$cmd"
    GROUP_CMDS+=("$cmd")
done
for n in "${NOTES[@]:-}"; do
    [ -z "$n" ] && continue
    echo "$n"
done
if [ "${#GROUP_CMDS[@]}" -gt 0 ]; then
    echo "  (log out and back in for new group membership to take effect)"
fi
echo

if [ "$FIX" -eq 0 ]; then
    echo "Re-run with --fix to run these commands (after confirming)."
    exit 1
fi

read -r -p "Run the commands above now? [y/N] " reply
case "$reply" in
    [yY]*)
        if [ -n "$APT_CMD" ]; then
            eval "$APT_CMD"
        fi
        for cmd in "${GROUP_CMDS[@]:-}"; do
            [ -z "$cmd" ] && continue
            eval "$cmd"
        done
        for n in "${NOTES[@]:-}"; do
            [ -z "$n" ] && continue
            eval "$n"
        done
        ;;
    *)
        echo "Skipped."
        exit 1
        ;;
esac
