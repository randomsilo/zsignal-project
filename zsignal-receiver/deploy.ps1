# Copy zsignal (codec) and zsignal-receiver to the Orange Pi, then build and
# (re)start its Docker container there.
#   .\zsignal-receiver\deploy.ps1                  # default device
#   .\zsignal-receiver\deploy.ps1 -Device root@192.168.1.50
#   .\zsignal-receiver\deploy.ps1 -SkipUp          # copy only, don't build/restart
# Requires passwordless SSH (see SSH.md) and Docker installed on the device (setup.sh).

param(
    [string]$Device = "root@192.168.1.199",
    [string]$Dest = "/opt/zsignal",
    [switch]$SkipUp
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "Deploying to ${Device}:${Dest} ..."
ssh $Device "mkdir -p $Dest"
if ($LASTEXITCODE -ne 0) { throw "ssh to $Device failed" }

# tar (built into Windows 10+) streams everything needed for the Docker build
# in one connection and skips caches.
tar -C $projectRoot --exclude=__pycache__ --exclude=*.pyc -cf - zsignal zsignal-receiver docker-compose.yml |
    ssh $Device "tar -xf - -C $Dest && find $Dest -name '*.sh' -exec sed -i 's/\r$//' {} +"
if ($LASTEXITCODE -ne 0) { throw "copy failed" }

ssh $Device "ls $Dest $Dest/zsignal-receiver"

if (-not $SkipUp) {
    Write-Host "Building and starting the zsignal-receiver container ..."
    ssh $Device "cd $Dest && docker compose build zsignal-receiver && docker compose up -d zsignal-receiver"
    if ($LASTEXITCODE -ne 0) { throw "docker compose build/up failed" }
}

Write-Host "Done."
