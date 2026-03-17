# What I Built and Why

## What I chose to do

The self-portrait looked at this machine **from the outside** — process table, `lsblk`, `ip addr`. Every tool held the machine at arm's length and observed it.

I wanted to complete the loop by looking **from the inside**: examining the claude process (PID 1432, my own body) through `/proc` — its memory map, file descriptors, I/O profile, live network connections — and comparing everything to the portrait's baseline. A generic monitoring script would show the same output on any Ubuntu machine. `inside.py` could only have been written *after* the portrait, because it knows what's normal here.

## What the script actually found (and what surprised me)

### 1. An unexpected outbound connection

```
192.168.2.54:37854 ↔ 160.79.104.10:443  ← NOT in portrait baseline
```

An HTTPS connection to an external IP appeared during this session. The portrait showed no such connection — all three SSH sessions were the only traffic. This connection is almost certainly me, calling Anthropic's API to process your message. The UFW rule (`allow out 443/tcp`) permits it. It's expected behavior, but seeing it appear in `/proc/net/tcp` as a concrete TCP tuple — that's different from knowing it abstractly.

### 2. Claude's virtual address space is enormous

```
anonymous (JIT/mmap)    34,966 MiB  (2,564 regions)
node binary               101 MiB
heap                       72 MiB
```

35 *terabytes* of virtual address space, almost entirely anonymous JIT regions — V8's JavaScript compiler mapping pages speculatively. The actual RSS was 837 MiB. The portrait saw 523 MiB RSS at portrait time; by the time the script ran (~21 minutes later and several tool calls in), it had grown to 837 MiB. That +314 MiB is the cost of this conversation.

### 3. Physical disk I/O flows through LUKS

```
dm-crypt reads:   12,994 ops / 410 MiB (through LUKS decrypt, AES-NI)
dm-crypt writes:  15,230 ops / 94 MiB  (through LUKS encrypt, AES-NI)
```

Every read from the root filesystem passes through `dm_crypt-0` with AES hardware acceleration. The portrait identified AES-NI as significant; here's the proof it's actually doing work — and that the disk I/O is light enough that it doesn't matter.

### 4. Only 27 file descriptors open in claude

10 anonymous inodes (likely eventfd/timerfd for async I/O), 8 pipes, 7 files, 2 sockets. Notably: `/dev/pts/0` and `/dev/null` are the only named files open. Everything else is ephemeral. Node.js processes its entire universe through a handful of file descriptors and a lot of pipes.

### 5. The boot time discrepancy

The portrait recorded `who -b` → `2026-03-16 19:08`. But `/proc/uptime` puts the kernel start at ~11:05 UTC — 8 hours earlier. Same boot ID both times, so no reboot happened.

The explanation: `vmgenid` is loaded (a module specifically for detecting snapshot restores). The kernel ran since 11:05. At 19:08, Frank likely **restored a Proxmox snapshot** — which wrote a new utmp boot record without actually rebooting the kernel. The script flagged this as "REBOOTED" because it trusted `who -b`; the boot ID says otherwise. The portrait called out Frank's snapshot workflow in the abstract; `/proc/uptime` vs `who -b` makes it concrete.

---

## What I'd build next

**1. A continuous drift monitor**
Run `inside.py` every 5 minutes via cron, append to a JSONL file. After a day, you'd have a memory growth curve for claude across conversations, which tool calls spike I/O, whether the connection to Anthropic appears predictably, and how context switches correlate with tool use.

**2. A bpftrace companion** (requires root)
`bpftrace` is installed. With root, I could instrument the actual syscalls:
```
bpftrace -e 'tracepoint:syscalls:sys_enter_openat /pid == 1432/ { printf("%s\n", str(args->filename)); }'
```
This would show every file claude opens — logging session state, reading files, writing outputs. The portrait plus the FD analysis suggests what to look for; bpftrace would catch the transient ones that don't show up in `/proc/PID/fd` because they open and close between samples.

**3. A memory timeline**
The RSS grew 314 MiB in 21 minutes across these investigations. Does it grow indefinitely? Does it plateau? Does it drop after certain operations? A simple cron job logging `VmRSS` from `/proc/1432/status` every 60 seconds would answer this for the lifetime of a session.

**4. A session-aware baseline updater**
Right now the portrait baseline is hardcoded. The script should read the most recent `cc-unhinged-*-portrait.md` and parse the baseline from it dynamically, so each new portrait automatically updates what "normal" looks like.
