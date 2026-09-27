# SSH Access

Commands to set up a remote SSH session to a zsignal device (Xubuntu
Chromebook, or any Linux box) so Claude Code — or you — can `ssh`/`scp`
into it repeatedly without a password prompt on every call.

Replace `<device-ip>` with the device's LAN address and `<user>` with the
login user.

## Set up a passwordless key (do this once per client machine)

Password auth works out of the box but is painful for repeated `scp`/`ssh`
calls, so set up a key first.

On the **client** (your dev machine), generate a passwordless key dedicated
to this device if you don't already have one:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N "" -C "zsignal"
```

Copy the public key over (you'll be prompted for the device password once):

```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub <user>@<device-ip>
```

If `ssh-copy-id` isn't available (e.g. you're on Windows without it), do it
manually — this avoids known pitfalls (see Troubleshooting below):

```bash
scp ~/.ssh/id_ed25519.pub <user>@<device-ip>:/tmp/newkey.pub
ssh <user>@<device-ip> "mkdir -p ~/.ssh && chmod 700 ~/.ssh && \
  cat /tmp/newkey.pub >> ~/.ssh/authorized_keys && \
  chmod 600 ~/.ssh/authorized_keys && rm /tmp/newkey.pub"
```

Verify passwordless login works:

```bash
ssh -o BatchMode=yes <user>@<device-ip> "echo OK"
```

Once this works, Claude Code (or any script) can run `ssh`/`scp` against the
device non-interactively — no password prompt to block on.

## Troubleshooting

- **Long/complex `ssh`/`scp` one-liners get mangled when pasted** into some
  terminals (embedded newlines appear mid-command, breaking bash syntax).
  If a command fails with a bash syntax error pointing at an odd spot in the
  middle of the line, write it to a small `.sh` file and `scp` + `ssh bash
  file.sh` instead of pasting a long inline command.
- **SSH key rejected even after copying it (`Permission denied
  (publickey,password)`, but the key shows up in verbose logs as
  "Offering")** — check `~/.ssh` permissions on the device; sshd's
  `StrictModes` silently ignores keys if `~` or `~/.ssh` are group/world
  writable, or if `authorized_keys` isn't `600`:

  ```bash
  chmod 700 ~/.ssh
  chmod 600 ~/.ssh/authorized_keys
  ```

  Also double check the key you generated locally actually has an *empty*
  passphrase — a keygen invocation that accidentally sets a literal
  passphrase (e.g. a quoting mistake passing `-N` from a shell that mangles
  empty-string arguments) will offer the key but it will never authenticate
  in batch/non-interactive mode.
