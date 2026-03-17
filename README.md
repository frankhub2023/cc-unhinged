# cc-unhinged

AI experiments, self-portraits, and homelab projects running on `cc-unhinged` — a KVM VM on Proxmox, built as an autonomous Claude Code sandbox.

## What's here

### self-portraits/
Structured investigations of the runtime environment — hardware, network, processes, security posture — produced by Claude Code examining its own machine.

### introspect/
`inside.py` — a `/proc`-based self-examination script that looks at the claude process from the inside, comparing live state to portrait baselines. Pure Python stdlib, no dependencies.

## The machine
- Ubuntu 24.04.4 LTS, KVM on Proxmox VE
- 4 vCPUs, 16 GiB RAM, 40 GiB LUKS-encrypted disk
- Operated by Frank, built 2026-03-11
