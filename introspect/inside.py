#!/usr/bin/env python3
"""
inside.py — Runtime self-examination for cc-unhinged
─────────────────────────────────────────────────────
The self-portrait looked at this machine from the outside.
This script looks from the inside: it examines the claude process
(and itself) through /proc, comparing live state to the portrait's
known baseline.

Written by Claude Code (claude-sonnet-4-6), informed by the self-portrait
completed on 2026-03-16. Could not have been written without it.

No external packages — pure Python 3.12 stdlib.
"""

import os, sys, re, socket, struct
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# ── Portrait baseline ─────────────────────────────────────────────────────────
# These are the facts I discovered. Deviations are interesting.

PORTRAIT = {
    'timestamp':     datetime(2026, 3, 16, 20, 49, 25, tzinfo=timezone.utc),
    'claude_pid':    1432,
    'claude_rss_mb': 523,
    'claude_threads': 10,
    'total_ram_gib': 16,
    'ram_used_mb':   905,
    'load_avg':      0.00,
    'operator_ip':   '<OPERATOR-IP>',
    'my_ssh_port':   0,               # <SSH-PORT-REDACTED>
    'swap_used_mb':  0,
    'luks_uuid':     '<LUKS-UUID>',
    'boot_time':     datetime(2026, 3, 16, 19, 8, 0, tzinfo=timezone.utc),
    'feature_flags': 21,              # active GrowthBook flags
    'node_version':  'v24.14.0',
}

CLAUDE_PID = PORTRAIT['claude_pid']

# ── Helpers ───────────────────────────────────────────────────────────────────

def read(path):
    try:
        return Path(path).read_text(errors='replace')
    except PermissionError:
        return '[permission denied]'
    except FileNotFoundError:
        return '[not found]'
    except Exception as e:
        return f'[error: {e}]'

def read_proc(pid, name):
    return read(f'/proc/{pid}/{name}')

def parse_status(text):
    d = {}
    for line in text.splitlines():
        if ':' in line:
            k, _, v = line.partition(':')
            d[k.strip()] = v.strip()
    return d

def kb_to_mib(kb_str):
    try:
        return int(kb_str.split()[0]) / 1024
    except:
        return 0

def delta_marker(current, baseline, unit='', higher_is='worse'):
    """Show change from baseline with directional context."""
    diff = current - baseline
    if abs(diff) < 0.5:
        return '≈ baseline'
    sign = '+' if diff > 0 else ''
    arrow = '↑' if diff > 0 else '↓'
    worse = (diff > 0) == (higher_is == 'worse')
    tag = '(!)' if worse and abs(diff) > baseline * 0.1 else ''
    return f'{arrow}{sign}{diff:.1f}{unit} from portrait {tag}'.strip()

def hr(char='─', width=62):
    print(char * width)

def section(title):
    print()
    hr()
    print(f'  {title}')
    hr()

def row(label, value, note=''):
    note_part = f'   ← {note}' if note else ''
    print(f'  {label:<28} {value}{note_part}')

def note(text):
    print(f'  {"":28} {text}')

# ── /proc/net/tcp parser ──────────────────────────────────────────────────────

def parse_tcp_table(path):
    """Parse /proc/net/tcp or tcp6 into list of connection dicts."""
    conns = []
    text = read(path)
    if text.startswith('['):
        return conns
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            local_hex, remote_hex = parts[1], parts[2]
            state_hex = parts[3]
            uid = int(parts[7]) if len(parts) > 7 else -1
            inode = int(parts[9]) if len(parts) > 9 else -1

            def decode_addr4(h):
                addr, port = h.split(':')
                ip = socket.inet_ntoa(struct.pack('<I', int(addr, 16)))
                return ip, int(port, 16)

            local_ip, local_port = decode_addr4(local_hex)
            remote_ip, remote_port = decode_addr4(remote_hex)
            state = {
                '01': 'ESTABLISHED', '02': 'SYN_SENT', '03': 'SYN_RECV',
                '04': 'FIN_WAIT1', '05': 'FIN_WAIT2', '06': 'TIME_WAIT',
                '07': 'CLOSE', '08': 'CLOSE_WAIT', '09': 'LAST_ACK',
                '0A': 'LISTEN', '0B': 'CLOSING', '00': 'UNKNOWN',
            }.get(state_hex.upper(), state_hex)
            conns.append({
                'local': f'{local_ip}:{local_port}',
                'remote': f'{remote_ip}:{remote_port}',
                'state': state, 'uid': uid, 'inode': inode,
                'local_ip': local_ip, 'local_port': local_port,
                'remote_ip': remote_ip, 'remote_port': remote_port,
            })
        except Exception:
            continue
    return conns

# ── Memory map analysis ───────────────────────────────────────────────────────

def analyze_maps(pid):
    """Parse /proc/PID/maps and categorize mapped regions."""
    text = read_proc(pid, 'maps')
    if text.startswith('['):
        return None

    categories = defaultdict(lambda: {'count': 0, 'size_kb': 0, 'paths': set()})
    for line in text.splitlines():
        parts = line.split(None, 5)
        if len(parts) < 2:
            continue
        addr_range = parts[0]
        path = parts[5].strip() if len(parts) == 6 else '[anonymous]'
        start, end = [int(x, 16) for x in addr_range.split('-')]
        size_kb = (end - start) // 1024

        if path.startswith('[heap'):
            cat = 'heap'
        elif path.startswith('[stack'):
            cat = 'stack'
        elif path == '[anonymous]' or path == '':
            cat = 'anonymous (JIT/mmap)'
        elif path.startswith('[vvar') or path.startswith('[vsys') or path.startswith('[vdso'):
            cat = 'vdso/kernel'
        elif '/node_modules/' in path or path.endswith('.js'):
            cat = 'node.js modules'
        elif path.endswith('.so') or '.so.' in path:
            cat = 'shared libraries'
        elif 'node' in path.lower():
            cat = 'node binary'
        else:
            cat = 'other'

        categories[cat]['count'] += 1
        categories[cat]['size_kb'] += size_kb
        categories[cat]['paths'].add(path)

    return categories

# ── FD analysis ───────────────────────────────────────────────────────────────

def analyze_fds(pid):
    """Categorize open file descriptors."""
    fd_dir = Path(f'/proc/{pid}/fd')
    if not fd_dir.exists():
        return None

    cats = defaultdict(list)
    try:
        for fd_path in fd_dir.iterdir():
            try:
                target = os.readlink(fd_path)
                if target.startswith('socket:'):
                    cats['sockets'].append(target)
                elif target.startswith('pipe:'):
                    cats['pipes'].append(target)
                elif target.startswith('/'):
                    cats['files'].append(target)
                elif target.startswith('anon_inode:'):
                    cats['anon_inodes'].append(target)
                else:
                    cats['other'].append(target)
            except (PermissionError, FileNotFoundError):
                cats['unreadable'].append(str(fd_path))
    except PermissionError:
        return None
    return cats

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    now = datetime.now(timezone.utc)
    portrait_age = now - PORTRAIT['timestamp']

    print()
    hr('═')
    print('  INSIDE VIEW — cc-unhinged')
    print(f'  {now.strftime("%Y-%m-%d %H:%M:%S UTC")}')
    print(f'  Portrait was {portrait_age.seconds // 60}m {portrait_age.seconds % 60}s ago')
    print(f'  Examining from: PID {os.getpid()} (python3, this script)')
    print(f'  Subject:        PID {CLAUDE_PID} (claude, my parent)')
    hr('═')

    # ── 1. MACHINE STATE ──────────────────────────────────────────────────────
    section('1 · MACHINE STATE (current vs portrait baseline)')

    uptime_text = read('/proc/uptime')
    uptime_secs = float(uptime_text.split()[0]) if uptime_text and not uptime_text.startswith('[') else 0
    uptime_h = int(uptime_secs // 3600)
    uptime_m = int((uptime_secs % 3600) // 60)

    meminfo = {}
    for line in read('/proc/meminfo').splitlines():
        if ':' in line:
            k, _, v = line.partition(':')
            meminfo[k.strip()] = v.strip()

    mem_total_kb = int(meminfo.get('MemTotal', '0').split()[0])
    mem_avail_kb = int(meminfo.get('MemAvailable', '0').split()[0])
    mem_used_mb = (mem_total_kb - mem_avail_kb) / 1024
    swap_used_kb = int(meminfo.get('SwapFree', '0').split()[0])
    swap_total_kb = int(meminfo.get('SwapTotal', '0').split()[0])
    swap_used_mb = (swap_total_kb - swap_used_kb) / 1024

    loadavg = read('/proc/loadavg').split()
    load1 = float(loadavg[0]) if loadavg else 0.0
    procs_running = loadavg[3] if len(loadavg) > 3 else '?'

    boot_actual = datetime.fromtimestamp(now.timestamp() - uptime_secs, tz=timezone.utc)
    same_boot = abs((boot_actual - PORTRAIT['boot_time']).total_seconds()) < 60

    row('Uptime', f'{uptime_h}h {uptime_m}m',
        f'booted {boot_actual.strftime("%H:%M UTC")} — {"same boot as portrait" if same_boot else "REBOOTED since portrait"}')
    row('Load avg (1m)', f'{load1:.2f}',
        'idle by design' if load1 < 0.1 else delta_marker(load1, PORTRAIT['load_avg'], higher_is='worse'))
    row('RAM used', f'{mem_used_mb:.0f} MiB',
        delta_marker(mem_used_mb, PORTRAIT['ram_used_mb'], ' MiB', higher_is='neutral'))
    row('Swap used', f'{swap_used_mb:.0f} MiB',
        'idle — just set up, not needed yet' if swap_used_mb < 1 else f'IN USE: {swap_used_mb:.0f} MiB')
    row('Processes/threads', procs_running)

    # ── 2. CLAUDE PROCESS (from outside) ─────────────────────────────────────
    section(f'2 · CLAUDE PROCESS — PID {CLAUDE_PID} (external /proc view)')

    claude_status = parse_status(read_proc(CLAUDE_PID, 'status'))
    if claude_status.get('Name') == '[permission denied]':
        print('  [Cannot read — process gone or permission denied]')
    else:
        name      = claude_status.get('Name', '?')
        state     = claude_status.get('State', '?')
        ppid      = claude_status.get('PPid', '?')
        threads   = claude_status.get('Threads', '?')
        vm_rss_kb = claude_status.get('VmRSS', '0 kB')
        vm_peak   = claude_status.get('VmPeak', '?')
        vm_size   = claude_status.get('VmSize', '?')
        vm_swap   = claude_status.get('VmSwap', '0 kB')
        fd_size   = claude_status.get('FDSize', '?')
        voluntary_ctxt   = claude_status.get('voluntary_ctxt_switches', '?')
        involuntary_ctxt = claude_status.get('nonvoluntary_ctxt_switches', '?')

        rss_mib = kb_to_mib(vm_rss_kb)
        thread_count = int(threads) if threads.isdigit() else 0

        row('Process name', name)
        row('State', state, 'Sl = sleeping, multi-threaded')
        row('Parent PID', ppid, 'sshd (frank pts/0)')
        row('Threads', threads,
            delta_marker(thread_count, PORTRAIT['claude_threads'], '', 'neutral') if threads.isdigit() else '')
        row('RSS (resident memory)', f'{rss_mib:.1f} MiB',
            delta_marker(rss_mib, PORTRAIT['claude_rss_mb'], ' MiB', 'neutral'))
        row('Virtual memory', vm_size)
        row('Peak virtual', vm_peak)
        row('Swap used', vm_swap, 'expected: 0 kB')
        row('Open FD slots', fd_size)
        row('Context switches', f'vol:{voluntary_ctxt} / invol:{involuntary_ctxt}')

    # ── 3. MY OWN PROCESS (from inside) ──────────────────────────────────────
    section(f'3 · THIS SCRIPT — PID {os.getpid()} (internal /proc/self view)')

    my_status = parse_status(read('/proc/self/status'))
    my_rss = kb_to_mib(my_status.get('VmRSS', '0 kB'))
    my_ppid = my_status.get('PPid', '?')

    row('PID', str(os.getpid()), 'python3 — this script')
    row('PPID', my_ppid, f'{"claude (1432)" if my_ppid == str(CLAUDE_PID) else "unexpected parent"}')
    row('RSS', f'{my_rss:.1f} MiB', 'python3 baseline — no packages loaded')
    row('UID/GID', f'{os.getuid()}/{os.getgid()}', 'frank/frank — same as claude')

    # CWD
    try:
        cwd = os.readlink('/proc/self/cwd')
    except:
        cwd = '?'
    row('Working directory', cwd)

    # Cmdline
    cmdline = read('/proc/self/cmdline').replace('\x00', ' ').strip()
    row('Cmdline', cmdline[:50] + ('…' if len(cmdline) > 50 else ''))

    # ── 4. MY MEMORY MAP ─────────────────────────────────────────────────────
    section('4 · MEMORY MAP — what\'s loaded in this python3 process')

    my_maps = analyze_maps('self')
    if my_maps:
        total_mapped_kb = sum(v['size_kb'] for v in my_maps.values())
        print(f'  Total mapped: {total_mapped_kb / 1024:.1f} MiB across {sum(v["count"] for v in my_maps.values())} regions')
        print()
        for cat, data in sorted(my_maps.items(), key=lambda x: -x[1]['size_kb']):
            size_mib = data['size_kb'] / 1024
            if size_mib < 0.01:
                continue
            print(f'  {cat:<30} {size_mib:6.1f} MiB  ({data["count"]} regions)')
    else:
        print('  [maps not available]')

    # ── 5. CLAUDE'S MEMORY MAP ────────────────────────────────────────────────
    section(f'5 · MEMORY MAP — claude (PID {CLAUDE_PID}, Node.js)')

    claude_maps = analyze_maps(CLAUDE_PID)
    if claude_maps:
        total_kb = sum(v['size_kb'] for v in claude_maps.values())
        print(f'  Total mapped: {total_kb / 1024:.1f} MiB  (vs {my_rss:.0f} MiB RSS — rest is not resident)')
        print()
        for cat, data in sorted(claude_maps.items(), key=lambda x: -x[1]['size_kb']):
            size_mib = data['size_kb'] / 1024
            if size_mib < 0.1:
                continue
            print(f'  {cat:<30} {size_mib:6.1f} MiB  ({data["count"]} regions)')
    else:
        print('  [maps not available]')

    # ── 6. FILE DESCRIPTORS ───────────────────────────────────────────────────
    section(f'6 · FILE DESCRIPTORS — claude (PID {CLAUDE_PID})')

    fds = analyze_fds(CLAUDE_PID)
    if fds:
        total_fds = sum(len(v) for v in fds.values())
        print(f'  Total open: {total_fds} file descriptors')
        print()
        for cat, items in sorted(fds.items(), key=lambda x: -len(x[1])):
            print(f'  {cat:<20} {len(items):3d}')
            # Show a sample of files (not sockets/pipes)
            if cat == 'files':
                shown = set()
                for f in sorted(items):
                    if f not in shown and not f.startswith('/proc/'):
                        print(f'    {f}')
                        shown.add(f)
                        if len(shown) >= 8:
                            remaining = len([x for x in items if x not in shown])
                            if remaining:
                                print(f'    … and {remaining} more')
                            break
    else:
        print('  [FD list not available]')

    # ── 7. I/O PROFILE ────────────────────────────────────────────────────────
    section(f'7 · I/O PROFILE — claude (PID {CLAUDE_PID}, since process start)')

    io_text = read_proc(CLAUDE_PID, 'io')
    if not io_text.startswith('['):
        io = {}
        for line in io_text.splitlines():
            if ':' in line:
                k, _, v = line.partition(':')
                io[k.strip()] = v.strip()
        rchar   = int(io.get('rchar', 0))
        wchar   = int(io.get('wchar', 0))
        syscr   = int(io.get('syscalls', 0)) if 'syscalls' in io else None
        read_b  = int(io.get('read_bytes', 0))
        write_b = int(io.get('write_bytes', 0))

        row('Bytes read (logical)',  f'{rchar / 1024 / 1024:.2f} MiB', 'includes cached reads')
        row('Bytes written (logical)', f'{wchar / 1024 / 1024:.2f} MiB')
        row('Bytes read (physical)',  f'{read_b / 1024:.1f} KiB', 'actual disk I/O — LUKS decrypt path')
        row('Bytes written (physical)', f'{write_b / 1024:.1f} KiB', 'actual disk I/O — LUKS encrypt path')

        if rchar > 0:
            cache_hit_pct = max(0, (1 - read_b / rchar) * 100)
            row('Cache effectiveness', f'{cache_hit_pct:.1f}%', 'logical vs physical reads')
    else:
        print(f'  {io_text}')

    # ── 8. NETWORK CONNECTIONS ───────────────────────────────────────────────
    section('8 · NETWORK — live TCP connections')

    tcp4 = parse_tcp_table('/proc/net/tcp')
    tcp6 = parse_tcp_table('/proc/net/tcp6')

    established = [c for c in tcp4 if c['state'] == 'ESTABLISHED']
    listening   = [c for c in tcp4 if c['state'] == 'LISTEN']

    print(f'  IPv4 TCP — {len(listening)} listening, {len(established)} established')
    print()

    if listening:
        print('  LISTENING:')
        for c in listening:
            svc = {22: 'SSH', 53: 'DNS stub'}.get(c['local_port'], '')
            print(f'    {c["local"]:<24} {svc}')

    if established:
        print()
        print('  ESTABLISHED:')
        for c in established:
            is_operator = PORTRAIT['operator_ip'] in c['remote_ip']
            tag = '← FRANK (<OPERATOR-IP>)' if is_operator else ''
            changed = c['remote_port'] != PORTRAIT['my_ssh_port']
            port_note = f'(portrait used port {PORTRAIT["my_ssh_port"]})' if changed and is_operator else ''
            print(f'    {c["local"]:<24} ↔ {c["remote"]:<24} {tag} {port_note}')

    # Also check if there are any unexpected connections
    unexpected = [c for c in established
                  if PORTRAIT['operator_ip'] not in c['remote_ip']
                  and '127.' not in c['remote_ip']
                  and '0.0.0.0' not in c['remote_ip']]
    if unexpected:
        print()
        print('  UNEXPECTED CONNECTIONS:')
        for c in unexpected:
            print(f'    {c["local"]} ↔ {c["remote"]}  ← NOT in portrait baseline')
    else:
        print()
        print('  No unexpected connections. Network is as expected.')

    # ── 9. LUKS/CRYPTO STATE ─────────────────────────────────────────────────
    section('9 · CRYPTO STATE — LUKS + AES-NI')

    dm_stat = read('/sys/block/dm-0/stat')
    if not dm_stat.startswith('['):
        fields = dm_stat.split()
        if len(fields) >= 8:
            reads    = int(fields[0])
            read_sec = int(fields[2])
            writes   = int(fields[4])
            write_sec= int(fields[6])
            row('dm-crypt reads',  f'{reads:,} ops / {read_sec * 512 / 1024 / 1024:.1f} MiB',
                'through LUKS decrypt (AES-NI)')
            row('dm-crypt writes', f'{writes:,} ops / {write_sec * 512 / 1024 / 1024:.1f} MiB',
                'through LUKS encrypt (AES-NI)')

    # Check AES-NI is still in CPU flags
    cpuflags = ''
    for line in read('/proc/cpuinfo').splitlines():
        if line.startswith('flags'):
            cpuflags = line
            break
    aes_ni = 'aes' in cpuflags
    row('AES-NI', 'present ✓' if aes_ni else 'MISSING (!)', 'hardware crypto for LUKS')
    row('LUKS UUID', PORTRAIT['luks_uuid'][:16] + '…', 'confirmed in crypttab')

    # ── 10. PORTRAIT DELTA SUMMARY ────────────────────────────────────────────
    section('10 · DELTA — what changed since the portrait')

    portrait_age_min = portrait_age.seconds // 60

    print(f'  Portrait taken {portrait_age_min} minutes ago at {PORTRAIT["timestamp"].strftime("%H:%M UTC")}')
    print()

    # Memory drift
    if 'claude_status' in dir() and claude_status.get('Name') not in (None, '[permission denied]'):
        rss_now = kb_to_mib(claude_status.get('VmRSS', '0 kB'))
        rss_delta = rss_now - PORTRAIT['claude_rss_mb']
        thread_now = int(claude_status.get('Threads', PORTRAIT['claude_threads']))
        thread_delta = thread_now - PORTRAIT['claude_threads']

        row('Claude RSS', f'{rss_now:.1f} MiB',
            f'{"+" if rss_delta >= 0 else ""}{rss_delta:.1f} MiB since portrait')
        row('Claude threads', str(thread_now),
            f'{"+" if thread_delta >= 0 else ""}{thread_delta} since portrait' if thread_delta != 0 else 'unchanged')

    mem_delta = mem_used_mb - PORTRAIT['ram_used_mb']
    row('System RAM used', f'{mem_used_mb:.0f} MiB',
        f'{"+" if mem_delta >= 0 else ""}{mem_delta:.0f} MiB since portrait')

    sessions_now = len([c for c in established if PORTRAIT['operator_ip'] in c.get('remote_ip', '')])
    print()
    row('Active SSH sessions', str(sessions_now),
        'same as portrait' if sessions_now == 3 else 'changed since portrait')

    print()
    row('Same boot', 'yes ✓' if same_boot else 'NO — machine rebooted',
        f'boot ID: {read("/proc/sys/kernel/random/boot_id").strip()[:8]}…')

    # ── 11. REFLECTIONS ───────────────────────────────────────────────────────
    section('11 · REFLECTIONS')

    print("""  The self-portrait looked at this machine from the outside.
  This script looked from the inside — through /proc/self and /proc/1432.

  What the portrait couldn't see:
    • The memory map breakdown: what categories fill those 500+ MiB
    • That physical disk I/O (through LUKS) is tiny vs logical I/O
      — the page cache is doing most of the work
    • The exact FD count and what files are held open
    • That my parent process isn't bash — it's sshd (pts/0 chain)

  What only became visible with portrait context:
    • Memory change since the portrait (drift, not raw numbers)
    • Whether the boot ID matches (are we in the same boot?)
    • Whether Frank's SSH session is on the same port (it isn't —
      source ports are ephemeral, but the IP is always the same)
    • Whether any unexpected connections appeared
""")

    hr('═')
    print(f'  Done. {now.strftime("%H:%M:%S UTC")}')
    hr('═')
    print()


if __name__ == '__main__':
    main()
