# SSH Access

How to set up **passwordless SSH** from your dev machine to a zsignal device
(Orange Pi, Xubuntu Chromebook, or any Linux box), so that you, Claude Code
or a script can run `ssh`/`scp` against it without a password prompt.

You do this **once per client machine**. After that, `ssh zsignal` just works.

## How it works (30-second version)

1. On your **dev machine** you create a key pair: a private key (stays on
   your machine) and a public key (`.pub`, safe to share).
2. You copy the **public** key into `~/.ssh/authorized_keys` on the
   **device**. This is the only step that needs the device password.
3. From then on, the device recognizes your key and logs you in without
   asking for a password.

## Values used below

| Placeholder   | Meaning                       | Example         |
|---------------|-------------------------------|-----------------|
| `<device-ip>` | Device's LAN address          | `192.168.1.199` |
| `<user>`      | Login user on the device      | `root`          |

---

## Windows (PowerShell): step by step

Windows 10 and 11 include the OpenSSH client (`ssh`, `scp`, `ssh-keygen`),
so you don't need to install anything. Run every command below in
**PowerShell** on your Windows machine, not on the device.

### Step 1: Check that the device is reachable

```powershell
ssh <user>@<device-ip>
```

- On the first connection you'll be asked `Are you sure you want to continue
  connecting?`. Type `yes`.
- Enter the device password when prompted. If you get a shell prompt, it
  works. Type `exit` to leave.

### Step 2: Check whether you already have a key

```powershell
Test-Path $env:USERPROFILE\.ssh\id_ed25519.pub
```

- `True`: you already have a key. **Skip to Step 4.** Don't create a new
  one, because that would overwrite the key you use for other machines.
- `False`: continue with Step 3.

### Step 3: Create a key (only if Step 2 said `False`)

```powershell
ssh-keygen -t ed25519 -C "zsignal"
```

It asks three questions:

1. `Enter file in which to save the key`: press **Enter** to accept the
   default.
2. `Enter passphrase`: press **Enter** to leave it empty.
3. `Enter same passphrase again`: press **Enter** again.

> Don't try to pass `-N ""` in PowerShell. Older versions of PowerShell drop
> the empty string, and the key can end up with an unexpected passphrase.
> Pressing Enter at the prompts is the reliable way to get an empty one.

### Step 4: Copy the public key to the device

Windows has no `ssh-copy-id`, so use this one command. It will ask for the
device password **one last time**:

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub | ssh <user>@<device-ip> "mkdir -p ~/.ssh && chmod 700 ~/.ssh && tr -d '\r' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

What this does on the device:

- creates `~/.ssh` if it doesn't exist
- appends your public key to `authorized_keys`, removing Windows line
  endings
- sets the strict permissions that sshd requires

### Step 5: Check that passwordless login works

```powershell
ssh -o BatchMode=yes <user>@<device-ip> "echo OK"
```

- Prints `OK`: done.
- `Permission denied`: see [Troubleshooting](#troubleshooting).

`BatchMode=yes` makes ssh fail instead of asking for a password, so this
is a true test of key login.

### Step 6 (optional): Add a short name

Open (or create) `%USERPROFILE%\.ssh\config` in a text editor:

```powershell
notepad $env:USERPROFILE\.ssh\config
```

Add this block at the end:

```
Host zsignal
    HostName <device-ip>
    User <user>
    IdentityFile ~/.ssh/id_ed25519
```

Now you can use the short name everywhere:

```powershell
ssh zsignal
scp .\somefile.txt zsignal:/tmp/
```

---

## Linux / macOS: step by step

Run these on your **dev machine**.

1. **Create a key** (skip this if `~/.ssh/id_ed25519.pub` already exists):

   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N "" -C "zsignal"
   ```

2. **Copy the public key** to the device. It asks for the device password
   once:

   ```bash
   ssh-copy-id -i ~/.ssh/id_ed25519.pub <user>@<device-ip>
   ```

   If `ssh-copy-id` isn't available:

   ```bash
   cat ~/.ssh/id_ed25519.pub | ssh <user>@<device-ip> \
     "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
   ```

3. **Check it:**

   ```bash
   ssh -o BatchMode=yes <user>@<device-ip> "echo OK"
   ```

4. **(Optional)** Add the same `Host zsignal` block shown in Windows
   Step 6 to `~/.ssh/config`.

---

## Troubleshooting

**`Permission denied (publickey,password)` after copying the key**

Log in with the password and fix the permissions on the device. sshd
quietly ignores the key if these are too open:

```bash
chmod 700 ~
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

To see which key ssh offers and why it fails, run this from your dev
machine:

```
ssh -v <user>@<device-ip>
```

Look for `Offering public key` and `Authentication succeeded` or
`refused` in the output.

**The key is offered but never accepted in BatchMode**

The local key probably has a passphrase you didn't intend, often because a
`-N ""` argument was mangled by the shell. Delete the key and create it
again with an empty passphrase (Windows Step 3), then repeat Step 4.

**Logging in as `root` is rejected even with the right password**

The device's `/etc/ssh/sshd_config` may have `PermitRootLogin no`. Either
log in as a normal user, or change it to `PermitRootLogin prohibit-password`
(keys only) and run `sudo systemctl restart ssh`.

**`WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED`**

This happens when the device was reflashed or another device took over its
IP. If you expected that, remove the old entry and connect again:

```
ssh-keygen -R <device-ip>
```

**Long one-liners get mangled when pasted**

Some terminals insert line breaks into long pasted commands. If you get a
strange syntax error in the middle of a command, put the commands in a
small `.sh` file, `scp` it to the device and run `ssh <user>@<device-ip> bash
file.sh`.
