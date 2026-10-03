#!/bin/bash
# Install/refresh the zsignal-receiver systemd service (run on the device as root,
# after deploy.ps1 has copied the files to /opt/zsignal).
set -e
install -m 644 /opt/zsignal/zsignal-receiver/zsignal-receiver.service /etc/systemd/system/zsignal-receiver.service
sed -i 's/\r$//' /etc/systemd/system/zsignal-receiver.service
systemctl daemon-reload
systemctl enable zsignal-receiver.service
systemctl restart zsignal-receiver.service
sleep 3
systemctl --no-pager status zsignal-receiver.service | head -12
