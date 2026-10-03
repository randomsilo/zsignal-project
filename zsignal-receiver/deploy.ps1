# Copy zsignal (codec) and zsignal-receiver to the Orange Pi.
#   .\zsignal-receiver\deploy.ps1                  # default device
#   .\zsignal-receiver\deploy.ps1 -Device root@192.168.1.50
# Requires passwordless SSH (see SSH.md).

param(
    [string]$Device = "root@192.168.1.199",
    [string]$Dest = "/opt/zsignal"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "Deploying to ${Device}:${Dest} ..."
ssh $Device "mkdir -p $Dest"
if ($LASTEXITCODE -ne 0) { throw "ssh to $Device failed" }

# tar (built into Windows 10+) streams both folders in one connection and skips caches.
tar -C $projectRoot --exclude=__pycache__ --exclude=*.pyc -cf - zsignal zsignal-receiver |
    ssh $Device "tar -xf - -C $Dest && find $Dest -name '*.sh' -exec sed -i 's/\r$//' {} +"
if ($LASTEXITCODE -ne 0) { throw "copy failed" }

ssh $Device "ls $Dest $Dest/zsignal-receiver"
Write-Host "Done."
