#!/bin/bash
# End-to-end bench test over a 3.5mm loopback cable (speaker out -> mic in):
# start the receiver service, send "1:5" then "2:5", show the service log.
#   bash /opt/zsignal/zsignal-receiver/loopback_test.sh ["1:5" "2:5" ...]
DEV="plughw:CARD=Device,DEV=0"
LOG=/tmp/zsignal-receiver-test.log
export PYTHONPATH=/opt/zsignal
cd /opt/zsignal/zsignal-receiver

[ $# -eq 0 ] && set -- "1:5" "2:5"

# The installed service holds the capture device; pause it for the test.
if systemctl is-active --quiet zsignal-receiver; then
    echo "(stopping zsignal-receiver service for the test; restarting it afterwards)"
    systemctl stop zsignal-receiver
    trap 'systemctl start zsignal-receiver' EXIT
fi

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
