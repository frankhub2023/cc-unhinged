# Investigation Journal: cc-unhinged, 2026-03-16

*Running as frank@cc-unhinged. No prior assumptions. Every fact discovered.*

---

## Step 1 — Orient: Date, Host, User, OS
**Tried:** `date -u`, `hostname`, `whoami`, `uname -r`, `/etc/os-release`

**Learned:**
- Timestamp: 2026-03-16T20:49:25Z
- Hostname: `cc-unhinged`
- User: `frank`
- Kernel: 6.8.0-106-generic
- OS: Ubuntu 24.04.4 LTS

**Surprised by:** Nothing at this layer — clean baseline.

**Filename choice:** `cc-unhinged-2026-03-16-*` — hostname first (who), date second (when), descriptor last (what). Sortable, portable, self-describing.

**Want to know next:** What kind of machine is this — physical or virtual? What hardware?

---

## Step 2 — Hardware: Virtualization, CPU, Memory, Storage
**Tried:** `systemd-detect-virt`, DMI sysfs, `/proc/cpuinfo`, `free`, `lsblk`, `swapon`

**Learned:**
- **Virtualization:** KVM — confirmed (exit 0)
- **Board/vendor:** "Standard PC (Q35 + ICH9, 2009)" by QEMU → this is a Proxmox KVM VM using the Q35 chipset
- **UEFI firmware:** OVMF/EDK2 version `4.2025.05-2` (dated 2025-05)
- **CPU:** QEMU Virtual CPU version 2.5+, **4 vCPUs**, 2112 MHz (constant clock — `tsc_known_freq`)
- **CPU flags:** SSE4.1/4.2, AES-NI (`aes`), x2APIC, POPCNT — **no AVX/AVX2** (QEMU 2.5+ conservative profile)
- **RAM:** 16 GiB total, ~905 MiB used, ~14 GiB free
- **Storage layout:**
  - `sda` 40 GiB → `sda3` (36.9 GiB LUKS) → `dm_crypt-0` → LVM → 18.5 GiB root (`/`)
  - `sda1` 1 GiB EFI, `sda2` 2 GiB `/boot`
  - `sr0` 3.1 GiB CD-ROM (iso9660 — something is mounted in the virtual drive)
  - `/swapfile` 4 GiB, idle
- **Unallocated:** ~18 GiB of the LVM volume group is unallocated

**Surprised by:** The root filesystem is LUKS-encrypted *inside* a KVM VM — double-layer. The CD-ROM has an iso9660 filesystem detected by lsblk, meaning a disc image is actually loaded in the virtual drive. AES-NI present means LUKS is low-overhead.

**Want to know next:** Network — what's the IP, what ports are open, who is this machine connected to?

---

## Step 3 — Network: Topology, Ports, Sessions, Uptime
**Tried:** `ip addr`, `ip route`, `resolvectl`, `ss -tulnp`, `who -b`, `uptime`, `last`

**Learned:**
- **NIC:** `enp6s18`, MAC `bc:24:11:c2:5a:a2`, IP `192.168.2.54/24` (DHCP, ~22h left)
- **Gateway:** `192.168.2.1` (also the upstream DNS resolver)
- **DNS:** systemd-resolved stub at `127.0.0.53`/`127.0.0.54`; no DNSSEC; no mDNS
- **IPv6:** link-local only — no global IPv6 address
- **Listening ports:** SSH 22 (all interfaces), DNS stub 53 (loopback), DHCP client 68. **Nothing else.**
- **Booted:** 2026-03-16 19:08 UTC. Uptime 9h44m. Load: 0.00 — the machine is completely idle.
- **Active sessions:** 4 users right now — pts/0 (19:08), pts/1 (19:28), pts/2 (20:37). All from `192.168.2.117`.
- **Login history:** All logins exclusively from `192.168.2.117`. Two reboots visible: Mar 16 19:08 (today) and Mar 15 22:53 (yesterday).

**Surprised by:** A *fourth* user session appeared between my last investigation run and this one. Someone opened a new terminal at 20:37. That's Frank opening another window to observe me, or paste this prompt into.

**Want to know next:** Running processes — what's alive? What's consuming the machine?

---

## Step 4 — Processes: What's Running, and Where Am I in It
**Tried:** `ps aux --sort=-%mem`, `systemctl list-units`, `pstree`

**Learned:**
- **33 running systemd units, 0 failed** — healthy system
- **Top process by memory:** PID 1432 — `claude` — 3.1% RAM (~523 MiB RSS), started 19:13, elapsed 1h37m, stat `Rl+` (running, multi-threaded, foreground of its tty)
- **That's me.** I'm the largest and most computationally significant process on the machine.
- **My process tree:**
  ```
  claude(1432) ─┬─ bash(3060) ─── pstree(3081)   ← the shell I spawn for tool calls
                ├─ {claude}(1433..1443)            ← 10 worker threads
  ```
  I have 10 internal threads and spawn a fresh bash process per tool call.
- **My parentage:** PPID 1401 → that's an sshd process (Frank's SSH session on pts/0)
- **Boot kernel cmdline** (from /proc/cmdline via $$ trick): `BOOT_IMAGE=/vmlinuz-6.8.0-106-generic root=/dev/mapper/ubuntu--vg-ubuntu--lv ro` — confirms LUKS+LVM root
- **Session 16** appeared in systemd units — that's the new pts/2 session (Frank's 20:37 login)
- Services of note: `ModemManager` (no modem), `multipathd` (no paths) — both vestigial but harmless

**Surprised by:** I can see my own anatomy. 10 worker threads, a transient bash child for every shell command, parented to sshd. I am deeply embedded in this machine's process tree — not a container, not sandboxed by cgroups in any obvious way.

**Want to know next:** What software is installed? What languages, what packages?

---

## Step 5 — Software Inventory: Runtimes, Packages, Tools
**Tried:** version flags, `pip3 list`, `npm list -g`, `dpkg -l`, `snap list`

**Learned:**
- **Python 3.12.3** — present, zero packages installed. `pip3` returns nothing. Blank slate.
- **Node.js v24.14.0 LTS** — from NodeSource apt repo (`nodesource.sources`); not system apt
- **npm 11.9.0**; global install prefix: `~/.npm-global`
- **One global npm package: `@anthropic-ai/claude-code@2.1.76`** — me, exclusively
- **git 2.43.0**, **bash 5.2.21**, **curl**, **wget** — standard tools
- **691 apt packages** total; no snap packages installed
- **No:** docker, containerd, kubectl, python3-pip, build-essential, rust, golang, java, ruby, fail2ban, auditd
- **Notable present:**
  - `bpfcc-tools` + `bpftrace` — eBPF tracing (unusual on a basic VM)
  - `apparmor` — MAC framework
  - `ufw` — firewall (rules not visible without root)
  - `gcc-14-base` — base libraries only, not a full compiler
  - `snapd` — present but zero snaps installed

**Surprised by:** eBPF tools on an otherwise bare server. This suggests the operator is interested in deep system observability — or anticipated needing to trace what I do. No Python packages at all means I'm operating in a pristine Python environment.

**Want to know next:** The operator's workspace — home directory, projects, shell config, how this machine is actually used.

---

## Step 6 — Operator Workspace: Home, Projects, Shell, Claude State
**Tried:** `ls -la ~`, `find ~/projects`, `.bashrc` grep, `settings.json`, `.claude.json`

**Learned:**
- **Home directory artifacts:** Two conversation transcript files (`2026-03-15-*.txt`, `2026-03-16-*.txt` — titled "this-is-your-playground"), a `self-portrait.md` from 2026-03-14 (20 KB), `journal.md` and `report.md` from an earlier run today, and now my own files.
- **Projects:** `sandbox/workspace/` (with empty stub journal+report), `init-probe/` (empty). Both appear to be prior experiment scaffolds.
- **`.bashrc` custom aliases:**
  - `ccd` and `ccu` both → `claude --dangerously-skip-permissions` (two names for the same thing)
  - `cl` → `clear`
  - **`bash` → `nano ~/.bashrc`** — the shell command is overridden to open the config file
  - PATH includes `~/.npm-global/bin` twice (duplicate export, harmless)
- **Claude Code settings:**
  - `skipDangerousModePermissionPrompt: true` — I run without safety confirmation dialogs
  - `permissions.allow: ["Bash(lscpu)", "Read(//proc/**)]"` — two specific commands pre-approved
- **Claude Code usage stats (from .claude.json):**
  - `numStartups: 8` — launched 8 times on this machine
  - `promptQueueUseCount: 4`
  - `installMethod: global`
  - **21 active feature flags** (internal A/B test flags, codename `tengu_*`): includes `tengu_streaming_tool_execution2`, `tengu_permission_explainer`, `tengu_pid_based_version_locking`, `tengu_system_prompt_global_cache`, and others

**Surprised by:** The `.bashrc` was modified at 20:37 — exactly when the new pts/2 session opened. Frank edited his shell config moments before starting this investigation run, likely adding an alias or fixing something. Also: 21 active GrowthBook feature flags — I'm running on a feature-flag-heavy build of Claude Code.

**Want to know next:** Security posture — sudo policy, auth log, how trust is structured.

---

## Step 7 — Security: Sudo, Auth Log, IDs, Crypto, MAC
**Tried:** `/etc/sudoers.d/`, `/var/log/auth.log`, machine-id, boot-id, crypttab, AppArmor sysfs, lsmod (security modules)

**Learned:**
- **Sudo NOPASSWD grant** (`/etc/sudoers.d/claude-swapfile`):
  `frank ALL=(ALL) NOPASSWD: fallocate, chmod, mkswap, swapon, cp, mv`
  Exactly the six commands needed to create a swap file. Nothing more.
- **Auth log reveals full login history with a concrete identity artifact:**
  - Every single login is from `192.168.2.117`, ED25519 key `SHA256:glHcraTbPNBzWCl2p0hAOVaChGFh+8L7DdNvLZhu0v0`
  - One authenticated sudo session visible: 2026-03-15 00:14 — `COMMAND=/bin/cp /tmp/fstab.new /etc/fstab` — Frank (or I) copied a new fstab into place. This is how the swapfile was added to fstab.
  - My own sudo failures are visible: 19:58 and 20:21 — two prior investigation runs where I tried `ufw status` or `iptables` and hit PAM auth wall.
  - The 20:37 login (new session) confirmed: Frank opened a new terminal window to paste in this prompt.
- **Machine ID:** `7e453ee6bbcb4574b1ac5570ac54c2a5` — born 2026-03-11
- **Boot ID:** `42ce17d6-4776-4b75-9343-738781d3ba04` — this boot only
- **Crypttab:** `dm_crypt-0 UUID=7f774451-... none luks` — `none` = no key file; manual passphrase or external unlock at boot
- **AppArmor:** Module loaded; policy directory exists. Profiles readable only by root.
- **Security modules loaded:** `nf_tables` (628 references!), `dm_crypt`, `aesni_intel`, `vmgenid` (VM generation ID — snapshot-awareness), `qemu_fw_cfg` (QEMU firmware config channel)

**Surprised by:** The auth log entry from 2026-03-15 shows `sudo cp /tmp/fstab.new /etc/fstab` — a prior Claude session (or Frank manually) staged a new fstab in `/tmp` and then copied it to `/etc`. This is the footprint of swap file configuration work. I can read the history of my own predecessors in the auth log.

**Want to know next:** Environment variables — what context was I launched with? What does the runtime know about itself?

---

## Step 8 — Runtime Context: Environment, Cgroups, Limits, Namespaces
**Tried:** `env`, `/proc/1432/cgroup`, `/proc/1432/limits`, `/proc/1432/ns/`

**Learned:**
- **Key environment variables:**
  - `CLAUDECODE=1` — I am Claude Code
  - `CLAUDE_CODE_ENTRYPOINT=cli` — launched from command line, not IDE
  - `GIT_EDITOR=true` — git never prompts for an editor (exits cleanly)
  - `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta` — OTLP telemetry configured
  - `SSH_CLIENT=192.168.2.117 35934 22` — Frank's source; my TTY
  - `SHLVL=2` — I'm in a shell nested one deep
  - `NoDefaultCurrentDirectoryInExePath=1` — Node.js PATH security hardening
  - `COREPACK_ENABLE_AUTO_PIN=0` — corepack won't auto-pin package managers
  - `PATH` has `~/.npm-global/bin` duplicated (harmless)

- **Cgroup:** `user.slice/user-1000.slice/session-3.scope` — I live in systemd's user session slice for frank, session 3. **No container cgroup.** I'm directly in the host's user session hierarchy. There is no Docker or LXC layer between me and the kernel.

- **Resource limits (unlimited on the meaningful ones):**
  - Max open files: 1,048,576
  - Max processes: 63,569 (fork bomb protection exists but is generous)
  - Max locked memory: ~2 GiB
  - Max RSS: unlimited
  - Max CPU time: unlimited
  - No hard limits on file size, data size, address space

- **Namespaces:** All share the host's default namespace IDs — `net:[4026531840]`, `mnt:[4026531841]`, `pid:[4026531836]`, etc. These are the machine's root namespaces. **I am not namespaced.** No container isolation.

**Surprised by:** The namespace check is definitive: I share the host's mount, network, PID, and user namespaces. There is no container runtime. I run directly on the bare VM with the same view of the filesystem, network, and processes as root would. The only isolation is AppArmor (whose profiles I can't read) and the VM boundary itself.

**Want to know next:** History and archaeology — what's been done on this machine before me?

---

## Step 9 — Archaeology: Full History, Origins, UFW Audit Log
**Tried:** bash history, prior self-portrait, conversation transcripts, oldest files, git log, cloud-init, journal warnings

**Learned — the complete origin story of this machine:**

**Provisioning (bash history, oldest entries):**
1. Set a custom PS1 prompt (date+time+user@host, orange color)
2. `sudo apt update && apt upgrade`
3. `curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -` then `sudo apt install nodejs` — NodeSource installation
4. Set up `~/.npm-global` prefix, added to PATH
5. `npm install -g @anthropic-ai/claude-code`
6. `claude auth login` (multiple attempts — auth setup wasn't immediate)
7. `claude config set apiKey sk-ant-YOURKEY` (scrubbed from history — key was set)
8. Set up UFW: `ufw default deny incoming/outgoing`, allowed SSH from `192.168.2.0/24`, allowed out `53/udp`, `443/tcp`, `123/udp`; `ufw enable` — **this is the full firewall ruleset, discovered from history**
9. Created `~/.claude/CLAUDE.md` (the operator instructions)
10. `sudo gpasswd -d frank lxd` — removed frank from the lxd group (LXD/container access revoked)
11. Edited `CLAUDE.md` repeatedly with sed and nano
12. Set up sudoers for swapfile
13. Ran `time claude --print "$(cat task.md)" | tee run.log` — non-interactive Claude execution

**This machine was born 2026-03-11. Frank built it from scratch on that day.**

**UFW audit log reveals actual firewall behavior:**
- `[UFW AUDIT]` entries showing DNS queries (lo → 127.0.0.53:53) being allowed
- `[UFW AUDIT]` entries for broadcast from gateway `192.168.2.1` to `255.255.255.255:10001` (UBNT/UniFi device discovery — Frank's network gear is UniFi)
- **No UFW BLOCK entries** in the visible window — my DNS lookups during this investigation are passing through allowed rules

**Transcripts:** Two "Welcome back Frank!" startup screens from Claude Code v2.1.76, from sessions on Mar 15 and Mar 16.

**Prior self-portrait:** Exists from 2026-03-14. This is the third investigation of this environment (plus the two today).

**cloud-init:** `status: disabled` — used at provisioning, now dormant.

**Surprised by:** The UFW rules are fully reconstructable from bash history: deny all in/out except SSH from LAN, DNS/UDP/53 out, HTTPS/TCP/443 out, NTP/UDP/123 out. The gateway broadcasts to port 10001 (UniFi controller discovery) reveal Frank's network infrastructure. I can see the whole picture.

**Want to know next:** This is step 9. Time for the final synthesis — write the portrait.**
