# MultiProxy Suite (mps.py)

A single-file, cross-platform (Windows / Linux / **Termux**) proxy manager with a rich terminal UI. It manages **Xray-core** profiles (VMess / VLESS / Trojan / Shadowsocks / …), **Psiphon**, **WireGuard**, **Hysteria2**, **sing-box**, **Tor**, **wg-quick** and **dnstt-client** — with subscriptions, groups, health testing, auto-switching, watchdog failover, load balancing and a live dashboard.

> **Why one file?** MultiProxy is deliberately shipped as a single `mps.py` script. There is no package structure, no virtualenv, and no install step to get wrong — you copy **one file** to any machine (Windows, Linux, or Termux), run it, and everything else (binaries, geo files, database) is set up automatically inside `mps_data/`. This keeps it easy to move between platforms and simple enough for less technical users to share and use.

---

## ✨ Features

| Area | What you get |
|---|---|
| **Profiles** | Import from subscription URLs, pasted links, bulk text, WireGuard `.conf` files, or add Psiphon/Tor profiles directly |
| **Groups & Subscriptions** | Organize profiles into groups; auto-refresh subscriptions on a schedule; activate/deactivate filters |
| **Health testing** | Concurrent TCP ping + real latency through the proxy, auto re-ping loop, speed test, QR export |
| **Automation** | Auto-switch to best profile, watchdog failover, timed auto-rotate, auto-connect after subscription add |
| **Routing** | Presets (`bypass_iran`, `bypass_lan`, `proxy_all`), Iran/China/Russia IP bypass, custom direct rules, geosite ad-block |
| **DPI bypass** | Xray fragment (length/interval), mux with configurable concurrency |
| **Psiphon** | Auto-downloaded official binary, direct/chain/dns modes, region select, upstream chaining through another profile |
| **Dashboard** | Compact two-column live panel: status, latency, uptime, public/exit IP, automation state, two-row hotkey bar |
| **Device integration** | 💻 OS Tools menu (9): TTS, notifications, clipboard, battery status, flush DNS — cross-platform (Windows SAPI/PowerShell, macOS, Linux, Termux) |
| **Data safety** | SQLite storage, optional SQLCipher encryption, JSON settings, automatic backups |

---

## 📦 Requirements

- **Python 3.9+**
- [`rich`](https://pypi.org/project/rich/) — auto-installed on first run
- `qrcode[pil]` — optional, for QR export (auto-detected)

Everything else (Xray-core, Psiphon tunnel core, geo files, Hysteria2, sing-box, Tor, wg-quick, dnstt-client) is **auto-downloaded** into `mps_data/bin/` by the built-in dependency manager.

---

## 🚀 Install & Run

```bash
pip install rich "qrcode[pil]"
python mps.py
```

On first run the app:

1. Checks/installs Python packages and required binaries (Xray + Psiphon + geo files).
2. Opens the **Setup Wizard** (also available from the main menu → `13`) that walks you through:
   dependencies → group → source (subscription URL / paste links / WireGuard file / Psiphon) → ports → routing → connect options → optional first connect.

---

## 🗺️ Main Menu

| # | Item | # | Item |
|---|------|---|------|
| 1 | Connect best profile | 8 | Routing menu |
| 2 | Profiles menu | 9 | 💻 OS Tools menu (Windows/Linux/macOS/Termux) |
| 3 | Groups menu | 10 | Backup menu |
| 4 | Subscriptions menu | 11 | 🔧 Dependencies |
| 5 | ⚙️ Settings | 12 | Psiphon auto-pilot |
| 6 | Disconnect | 13 | 🧙 Setup wizard |
| 7 | 📊 Live dashboard | 0 | Exit |

### 🔧 Dependencies menu (11)

Shows a status table (✓ path / ✗ missing / ✓ managed) for **Xray, Psiphon, Geo files, Hysteria2, sing-box, Tor, wg-quick, dnstt-client, Python packages, system packages**. Actions: install/reinstall a single item, install all missing (`a`), reinstall all (`r`).

Install behavior per component:

| Component | How it installs |
|---|---|
| **Xray-core** | Official GitHub release zip for your OS/arch; geo files fetched alongside |
| **Psiphon** | [psiphon-tunnel-core-binaries](https://github.com/Psiphon-Labs/psiphon-tunnel-core-binaries) repo — GitHub API first, then raw URL, then repo tarball |
| **Geo files** | `geoip.dat` / `geosite.dat` from the xray geo releases (size-validated) |
| **Hysteria2** | Official GitHub release binary |
| **sing-box** | Official GitHub release archive, binary extracted |
| **Tor** | Scrapes [dist.torproject.org](https://dist.torproject.org/torbrowser/) for the latest stable version, then downloads `tor-expert-bundle-<os>-<arch>-<ver>.tar.gz` and extracts `tor` (fallback versions pinned in code) |
| **dnstt-client** | Downloads the snapshot zip from [bamsoftware.com](https://www.bamsoftware.com/software/dnstt/) and **builds it with Go** (`go build ./dnstt-client`) — requires the Go toolchain on PATH |
| **wg-quick** | Linux/Termux only (`wireguard-tools` package); on Windows install the [official WireGuard client](https://www.wireguard.com/install/) separately |

### ⚙️ Settings (5) — categorized

| Category | Settings |
|---|---|
| 🌐 Network & Ports | SOCKS port(s), HTTP port, DNS, concurrency, timeout |
| 🛣️ Routing & DPI | routing preset, fragment, mux, geosite ad-block, load balancing + strategy |
| 🤖 Automation | auto-switch, failover (interval/max fails), auto-rotate, auto-connect, refresh intervals, auto-install |
| 🌐 Psiphon | mode, region, config URL, upstream profile, DNS source, use-DNS, safe-launch retries |
| 📱 Interface & Device | TTS, notifications, vibration, battery/screen-off aware, torch |
| 🔬 Advanced | Xray `-test` pre-check, audit log, SQLCipher key, skip subscription TLS verify |

### 📊 Live Dashboard (7)

```
┌────────────────────── 📊 MultiProxy ───────────────────────┐
│ Status     ● CONNECTED        Auto-Sw    ON                │
│ Profile    my-vless           Failover   ON                │
│ Protocol   VLESS              Load Bal.  OFF               │
│ Endpoint   example.com:443    Re-ping    4m 12s            │
│ Core       xray               Public IP  103.x.x.x         │
│ SOCKS5     127.0.0.1:10808                                 │
│ HTTP       127.0.0.1:10810                                 │
│ Latency    187 ms                                          │
│ Uptime     00:12:41                                        │
│ Rate       ↑ 240 KB/s  ↓ 1.0 MB/s                          │
│ Session    ↑ 50.0 MB  ↓ 512.0 MB                           │
│ ────────────────────────────────────────────────────────── │
│ Enter best   p pick   r re-ping                            │
│ d disconnect   q exit                                      │
└────────────────────────────────────────────────────────────┘
```

Hotkeys: **Enter** = connect best · **p** = pick profile (paginated, 10 per page — `n` next / `b` back / `q` cancel) · **r** = re-ping all · **d** = disconnect · **q** = exit.
The **Public IP** row shows your exit IP (fetched through the proxy via `api.ipify.org`, cached 2 min).
**Rate** shows live upload/download throughput and **Session** shows totals since connect (reset on every connect/disconnect). Throughput is measured with `psutil` when installed (auto-installed with Python packages), falling back to `/proc/net/dev` on Linux/Termux.

---

## 📁 File Layout

```
MultiProxy/
├── mps.py                  # the whole app
└── mps_data/
    ├── profiles.db         # SQLite (profiles, groups, subscriptions, logs)
    ├── settings.json       # persisted settings
    ├── mps.log             # application error log (all errors + tracebacks)
    ├── bin/                # auto-downloaded binaries (xray, psiphon-tunnel-core, …)
    ├── geo/                # geoip.dat / geosite.dat
    ├── logs/               # core + audit logs
    └── backups/            # backup archives
```

---

## 🌐 Subscription Sources

- **Subscription URLs** — base64 or plain-text lists of `vmess:// vless:// trojan:// ss:// hysteria2:// tuic:// socks:// wireguard:// psiphon://` links; auto-refreshed every N hours (configurable per subscription).
- **Paste links** — paste any number of links at once.
- **WireGuard `.conf`** — parsed into a profile automatically.
- **Psiphon** — created with one prompt (region + port); binary auto-installed.

---

## 📱 Termux Notes

```bash
pkg install python
pip install rich "qrcode[pil]"
python mps.py
```

- Binaries are downloaded for the detected architecture (`aarch64`/`arm`/`x86_64`).
- **OS Tools (9)** works on every platform: on Termux it uses `termux-api` tools; on Windows it uses built-in SAPI (TTS), PowerShell notifications and clipboard; on macOS `say`/`osascript`/`pbcopy`; on Linux `espeak`/`notify-send`/`wl-clipboard`/`xclip`.
- Battery-aware mode reduces test concurrency on low battery; screen-off-aware mode reduces it further.

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---|---|
| **Psiphon download 404** | The installer tries the GitHub API first, then raw URLs, then the binaries repo tarball. If all fail (network blocked), open **Dependencies (11) → Psiphon** to retry, or download `psiphon-tunnel-core` manually from [psiphon-tunnel-core-binaries releases](https://github.com/Psiphon-Labs/psiphon-tunnel-core-binaries/releases) into `mps_data/bin/`. |
| **Tor download 404** | The installer scrapes dist.torproject.org for the newest stable `tor-expert-bundle` tarball and falls back to pinned versions. If dist.torproject.org is blocked, download the bundle manually from [torproject.org/download/tor](https://www.torproject.org/download/tor/) and place `tor` / `tor.exe` in `mps_data/bin/`. |
| **dnstt-client build fails** | dnstt is compiled from source — install [Go](https://go.dev/dl/) and make sure `go` is on PATH, then retry from **Dependencies (11) → dnstt-client**. |
| **raw.githubusercontent.com TLS errors** | The app falls back to `api.github.com` / `codeload.github.com` mirrors automatically. |
| **Subscription fetch: `CERTIFICATE_VERIFY_FAILED` / hostname mismatch** | Some subscription servers serve broken certificates. Enable **Settings → Advanced → Skip subscription TLS verify** (`subscription_skip_tls_verify`) to bypass certificate validation for subscription downloads only (proxy traffic is unaffected). Background auto-refresh logs these errors quietly instead of spamming the console. |
| **Geo files too small / corrupt** | Dependencies menu → Geo files (always re-validates ≥8 MB geoip / ≥10 MB geosite). |
| **Xray fails to start** | Enable *Xray -test pre-check* in Settings → Advanced to see config errors before launch. |
| **Where are errors logged?** | Every error (including uncaught exceptions in the main thread and background threads) is written to `mps_data/mps.log` with timestamps and tracebacks. The console stays clean; screens are cleared between menus with a "Press Enter to continue…" pause so output is readable. |
| **DB encrypted / forgot key** | Settings → Advanced → SQLCipher key; changing it requires an app restart. |
| **Windows console Unicode errors** | Use Windows Terminal (UTF-8) instead of the legacy console. |

---

## 🔒 Privacy

All data stays local: SQLite DB + JSON settings under `mps_data/`. No telemetry. Psiphon and Xray cores are the official upstream binaries, verified by size and (when available) checksum.
