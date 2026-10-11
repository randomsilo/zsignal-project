#!/bin/bash
# End-to-end bench test over a 3.5mm loopback cable (speaker out -> mic in):
# start the receiver service, send "1:5" then "2:5", show the service log.
# Run via `docker compose run --rm --entrypoint bash zsignal-receiver
# loopback_test.sh` after `docker compose stop zsignal-receiver` (see
# README.md) -- PYTHONPATH and the working directory are already set by
# the image, so this only needs to run inside that container, not on the
# bare host.
DEV="plughw:CARD=Device,DEV=0"
LOG=/tmp/zsignal-receiver-test.log

[ $# -eq 0 ] && set -- "1:5" "2:5"

python3 -u -m zsignal_receiver.service -D "$DEV" > "$LOG" 2>&1 &
SVC=$!
sleep 2  # let the listener measure the noise floor

for cmd in "$@"; do
    echo ">>> sending $cmd"
    python3 -m zsignal send "$cmd" --no-ptt -D "$DEV" > /dev/null
    secs=${cmd#*:}
    sleep "$(python3 -c "print(float('$secs') + 2.5)")"
done

kill -TERM $SVC
wait $SVC
echo "----- service log -----"
cat "$LOG"
