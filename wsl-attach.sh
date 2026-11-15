#!/bin/bash
# Re-attach the Digirig to WSL2 and bring zsignal-web up with the right
# mixer levels. Run from WSL after a reboot, a replug, or `wsl --shutdown`.
#
#   ./wsl-attach.sh            attach, (re)start zsignal-web, set mixer
#   ./wsl-attach.sh --no-web   attach and stop there (e.g. for the native CLI)
#
# Finds the Digirig by VID:PID, so it still works after moving it to another
# USB port. Binding a new port needs an Administrator PowerShell; this script
# tells you the exact command when that's the case. See windows_wsl2.md.

set -u

START_WEB=1
[ "${1:-}" = "--no-web" ] && START_WEB=0

USBIPD="/mnt/c/Program Files/usbipd-win/usbipd.exe"
SERIAL_VIDPID="10c4:ea60"   # CP2102N (PTT)
AUDIO_VIDPID="0d8c:0012"    # C-Media USB audio
CARD="Device"

cd "$(dirname "$0")"

if [ ! -x "$USBIPD" ]; then
    echo "usbipd-win not found at $USBIPD -- see windows_wsl2.md section 1." >&2
    exit 1
fi

# Print "BUSID STATE" for the first connected device with this VID:PID.
lookup() {
    "$USBIPD" list | tr -d '\r' | awk -v id="$1" '
        /^Persisted:/ { exit }
        $2 == id {
            state = ($NF == "Attached") ? "Attached" : ($NF == "Shared") ? "Shared" : "NotShared"
            print $1, state; exit
        }'
}

need_bind=()
attached_any=0
for pair in "serial:$SERIAL_VIDPID" "audio:$AUDIO_VIDPID"; do
    name=${pair%%:*}; vidpid=${pair#*:}
    read -r busid state <<<"$(lookup "$vidpid")"
    if [ -z "${busid:-}" ]; then
        echo "[MISSING] Digirig $name ($vidpid) isn't plugged in, or Windows can't see it." >&2
        exit 1
    fi
    case "$state" in
        Attached)  echo "[OK]      $name $busid already attached" ;;
        Shared)    echo "[..]      attaching $name $busid"
                   out=$("$USBIPD" attach --wsl --busid "$busid" 2>&1) || { echo "$out" >&2; exit 1; }
                   attached_any=1 ;;
        NotShared) need_bind+=("$busid") ;;
    esac
done

if [ ${#need_bind[@]} -gt 0 ]; then
    echo
    echo "These need binding first (new USB port?). In an Administrator PowerShell run:"
    for b in "${need_bind[@]}"; do echo "    usbipd bind --busid $b"; done
    echo "then re-run ./wsl-attach.sh"
    exit 1
fi

# Wait for the device nodes to show up in WSL.
for _ in $(seq 20); do
    [ -e /dev/ttyUSB0 ] && [ -e "/proc/asound/$CARD" ] && break
    sleep 0.5
done
[ -e /dev/ttyUSB0 ]        && echo "[OK]      /dev/ttyUSB0"       || { echo "[MISSING] /dev/ttyUSB0" >&2; exit 1; }
[ -e "/proc/asound/$CARD" ] && echo "[OK]      ALSA card $CARD"    || { echo "[MISSING] ALSA card $CARD" >&2; exit 1; }

[ "$START_WEB" = 1 ] || exit 0

# Docker only passes through devices present at container start, so restart
# a running container if we just attached something.
if [ -n "$(docker compose ps -q --status running zsignal-web)" ]; then
    if [ "$attached_any" = 1 ]; then
        echo "[..]      restarting zsignal-web"
        docker compose restart zsignal-web >/dev/null 2>&1 || { docker compose restart zsignal-web; exit 1; }
    fi
else
    echo "[..]      starting zsignal-web"
    docker compose up -d zsignal-web >/dev/null 2>&1 || { docker compose up -d zsignal-web; exit 1; }
fi

# A fresh attach resets the Digirig to AGC on / mic 20 / speaker 27.
# Set from inside the container: it runs as root, so host group IDs don't matter.
docker compose exec -T zsignal-web sh -c "
    amixer -c $CARD cset name='Auto Gain Control' off &&
    amixer -c $CARD cset name='Mic Capture Volume' 12 &&
    amixer -c $CARD cset name='Speaker Playback Volume' 14" >/dev/null \
    && echo "[OK]      mixer: AGC off, mic 12 (0 dB), speaker 14 (-23 dB)" \
    || { echo "[FAIL]    setting mixer levels" >&2; exit 1; }

code=000
for _ in $(seq 20); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://localhost:5055/)
    [ "$code" = 200 ] && break
    sleep 0.5
done
[ "$code" = 200 ] && echo "[OK]      zsignal-web at http://localhost:5055" \
                  || { echo "[FAIL]    http://localhost:5055 returned $code" >&2; exit 1; }
