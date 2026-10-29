#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MultiProxy Suite — v2.5 (Final)                                            ║
║  v2.4 + 5 patches:                                                          ║
║    1. geosite_ads_block flag (default False)                                ║
║    2. category-ads-all conditional                                          ║
║    3. DNS simplified (no geosite:ir / geosite:geolocation-!cn)              ║
║    4. ensure_geo_files detects truncated files                              ║
║    5. ensure_psiphon fetches from repo tree (no releases exist) +           ║
║       Go source-build fallback for unsupported platforms                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import re
import json
import time
import shutil
import socket
import sqlite3
import asyncio
import base64
import subprocess
import tempfile
import urllib.parse
import urllib.request
import urllib.error
import ssl
import threading
import struct
import logging
import random
import string
import zipfile
import io
import hashlib
import queue
import platform as _platform
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Any
from contextlib import contextmanager

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm, IntPrompt
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
    from rich.rule import Rule
    from rich.theme import Theme
    from rich.align import Align
    from rich.live import Live
    from rich.markup import escape as rich_escape
    from rich import box
    from rich.columns import Columns
    from rich.text import Text
except ImportError:
    print("Installing rich...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich"])
    sys.exit(subprocess.call([sys.executable] + sys.argv))

try:
    import qrcode  # type: ignore
    _HAS_QR = True
except ImportError:
    _HAS_QR = False

try:
    import sqlcipher3  # type: ignore
    _HAS_SQLCIPHER = True
except ImportError:
    _HAS_SQLCIPHER = False

THEME = Theme({
    "title": "bold cyan", "success": "bold green", "fail": "bold red",
    "warn": "bold yellow", "info": "bold blue", "muted": "dim white",
})
console = Console(theme=THEME, highlight=False)


def _pause_for_output():
    """Pause so the user can read output before the next screen clear."""
    try:
        console.print("[dim]Press Enter to continue...[/dim]", end="")
        sys.stdin.readline()
        console.print()
    except Exception as e:
        logging.debug("pause_for_output failed: %s", e)

# =============================================================================
# PLATFORM DETECTION
# =============================================================================


def detect_platform() -> Dict[str, Any]:
    machine = (_platform.machine() or "").lower()
    if machine in ("amd64", "x86_64"):
        arch = "x86_64"
    elif machine in ("i386", "i686", "x86"):
        arch = "i686"
    elif machine in ("aarch64", "arm64"):
        arch = "aarch64"
    elif machine.startswith("arm"):
        arch = "armv7"
    else:
        arch = machine or "unknown"
    raw = sys.platform
    if raw.startswith("win") or os.name == "nt":
        os_id = "windows"
    elif raw == "darwin":
        os_id = "macos"
    elif ("ANDROID_ROOT" in os.environ or "TERMUX_VERSION" in os.environ
          or Path("/data/data/com.termux").is_dir()):
        os_id = "android"
    elif raw.startswith("linux"):
        os_id = "linux"
    elif raw.startswith(("freebsd", "openbsd", "netbsd")):
        os_id = "bsd"
    else:
        os_id = raw or "unknown"
    return {"os": os_id, "arch": arch}


PLATFORM = detect_platform()
EXE_SUFFIX = ".exe" if PLATFORM["os"] == "windows" else ""
TERMUX_PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
TERMUX = PLATFORM["os"] == "android"

# =============================================================================
# PATHS
# =============================================================================
VERSION = "2.5-final"
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "mps_data"
OUTPUT_DIR.mkdir(exist_ok=True)
DB_FILE = OUTPUT_DIR / "profiles.db"
SETTINGS_FILE = OUTPUT_DIR / "settings.json"
ACTIVE_CONFIG = OUTPUT_DIR / "active_xray.json"
ACTIVE_HY2 = OUTPUT_DIR / "active_hysteria.yaml"
ACTIVE_SINGBOX = OUTPUT_DIR / "active_singbox.json"
LOG_FILE = OUTPUT_DIR / "mps.log"
AUDIT_FILE = OUTPUT_DIR / "audit.log"
BACKUP_DIR = OUTPUT_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)
BIN_DIR = OUTPUT_DIR / "bin"
BIN_DIR.mkdir(exist_ok=True)
GEO_DIR = OUTPUT_DIR / "geo"
GEO_DIR.mkdir(exist_ok=True)

logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")


def _log_uncaught(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        return
    logging.error("Uncaught exception: %s\n%s",
                  exc_type.__name__,
                  "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))


sys.excepthook = _log_uncaught
threading.excepthook = lambda args: logging.error(
    "Uncaught thread exception: %s\n%s",
    getattr(args.exc_type, "__name__", str(args.exc_type)),
    "".join(traceback.format_exception(
        args.exc_type, args.exc_value, args.exc_traceback)))

DEFAULT_SETTINGS = {
    "socks_port": 10808, "socks_port_2": 10809, "http_port": 10810,
    "dns": "1.1.1.1", "concurrency": 20, "timeout": 3.0,
    "routing": "bypass_iran",
    "fragment": True, "fragment_length": "100-200", "fragment_interval": "10-20",
    "mux": True, "mux_concurrency": 8,
    "tts": True, "notify": True, "vibrate": True,
    "refresh_interval_hours": 8,
    "failover": False, "failover_interval_sec": 30, "failover_max_fails": 3,
    "auto_rotate_minutes": 0,
    "battery_aware": False, "battery_threshold": 20, "screen_off_aware": False,
    "random_subdomain": False, "custom_routing_rules": [],
    "china_bypass": False, "russia_bypass": False,
    "torch_on_connect": False, "torch_duration_ms": 1000,
    "auto_connect_after_sub": True,
    "load_balancing": False, "lb_strategy": "leastPing", "lb_observatory_interval": "30s",
    "sqlcipher_key": "", "audit_enabled": True,
    "auto_install": True,
    "xray_test_before_launch": False,
    "auto_refresh_profiles_minutes": 10,
    "auto_switch_enabled": True,
    "active_subscription_ids": [],
    "active_group_ids": [],
    "psiphon_mode": "direct",
    "psiphon_region": "",
    "psiphon_config_url": "",
    "psiphon_upstream_profile_id": None,
    "psiphon_dns_source": "",
    "psiphon_use_dns": False,
    "safe_launch_retries": 3,
    "iran_ip_bypass": True,
    "geosite_ads_block": False,
    "subscription_skip_tls_verify": False,
}

# ========== لیست دامنه‌های ایرانی (Bypass) ==========
IRAN_DOMAINS = [
    r"regexp:.*\.ir$",
    "domain:aparat.com", "domain:digikala.com", "domain:divar.ir",
    "domain:shad.ir", "domain:balad.ir", "domain:alibaba.ir",
    "domain:snapp.ir", "domain:tapsi.ir", "domain:cafebazaar.ir",
    "domain:myket.ir", "domain:namava.ir", "domain:filimo.com",
    "domain:telewebion.com", "domain:modiseh.com", "domain:bmi.ir",
    "domain:irancell.ir", "domain:mci.ir", "domain:rtl.ir",
    "domain:irib.ir", "domain:banks.ir", "domain:shaparak.ir",
]

# ========== رنج IPهای ایران (fallback اگر geoip نبود) ==========
IRAN_IP_RANGES = list(dict.fromkeys([
    "2.144.0.0/14", "5.1.0.0/16", "5.22.0.0/16", "5.23.0.0/16",
    "5.34.0.0/16", "5.52.0.0/16", "5.53.0.0/16", "5.62.0.0/16",
    "5.63.0.0/16", "5.72.0.0/16", "5.73.0.0/16", "5.74.0.0/16",
    "5.144.0.0/13", "5.190.0.0/16", "5.191.0.0/16", "5.198.0.0/16",
    "5.200.0.0/16", "5.201.0.0/16", "5.202.0.0/16", "5.210.0.0/16",
    "5.219.0.0/16", "5.22.0.0/16", "5.23.0.0/16", "5.238.0.0/16",
    "5.250.0.0/16", "5.253.0.0/16", "5.255.0.0/16", "31.2.0.0/16",
    "31.7.0.0/16", "31.14.0.0/16", "31.24.0.0/16", "31.25.0.0/16",
    "31.29.0.0/16", "31.40.0.0/16", "31.47.0.0/16", "31.56.0.0/16",
    "31.57.0.0/16", "31.58.0.0/16", "31.59.0.0/16", "37.32.0.0/16",
    "37.44.0.0/16", "37.49.0.0/16", "37.63.0.0/16", "37.75.0.0/16",
    "37.98.0.0/16", "37.114.0.0/16", "37.129.0.0/16", "37.130.0.0/16",
    "37.131.0.0/16", "37.148.0.0/16", "37.152.0.0/16", "37.153.0.0/16",
    "37.156.0.0/16", "37.191.0.0/16", "37.202.0.0/16", "37.221.0.0/16",
    "37.228.0.0/16", "37.235.0.0/16", "37.254.0.0/16", "46.18.0.0/16",
    "46.21.0.0/16", "46.28.0.0/16", "46.32.0.0/16", "46.34.0.0/16",
    "46.38.0.0/16", "46.41.0.0/16", "46.51.0.0/16", "46.62.0.0/16",
    "46.100.0.0/16", "46.102.0.0/16", "46.143.0.0/16", "46.148.0.0/16",
    "46.164.0.0/16", "46.166.0.0/16", "46.167.0.0/16", "46.209.0.0/16",
    "46.224.0.0/16", "46.245.0.0/16", "46.248.0.0/16", "46.249.0.0/16",
    "46.251.0.0/16", "62.60.0.0/16", "62.102.0.0/16", "62.193.0.0/16",
    "62.204.0.0/16", "62.212.0.0/16", "62.220.0.0/16", "62.222.0.0/16",
    "62.228.0.0/16", "62.229.0.0/16", "62.230.0.0/16", "62.240.0.0/16",
    "77.36.0.0/16", "77.37.0.0/16", "77.74.0.0/16", "77.81.0.0/16",
    "77.104.0.0/16", "77.110.0.0/16", "77.237.0.0/16", "77.238.0.0/16",
    "77.245.0.0/16", "78.38.0.0/16", "78.39.0.0/16", "78.110.0.0/16",
    "78.111.0.0/16", "78.157.0.0/16", "78.158.0.0/16", "79.127.0.0/16",
    "79.132.0.0/16", "79.133.0.0/16", "79.170.0.0/16", "79.174.0.0/16",
    "79.175.0.0/16", "80.66.0.0/16", "80.71.0.0/16", "80.75.0.0/16",
    "80.191.0.0/16", "80.210.0.0/16", "80.231.0.0/16", "80.242.0.0/16",
    "80.250.0.0/16", "80.253.0.0/16", "81.12.0.0/16", "81.16.0.0/16",
    "81.21.0.0/16", "81.28.0.0/16", "81.29.0.0/16", "81.31.0.0/16",
    "81.33.0.0/16", "81.34.0.0/16", "81.35.0.0/16", "81.42.0.0/16",
    "81.44.0.0/16", "81.46.0.0/16", "81.48.0.0/16", "81.49.0.0/16",
    "81.51.0.0/16", "81.52.0.0/16", "81.53.0.0/16", "81.54.0.0/16",
    "81.55.0.0/16", "81.56.0.0/16", "81.57.0.0/16", "81.58.0.0/16",
    "81.59.0.0/16", "81.60.0.0/16", "81.61.0.0/16", "81.62.0.0/16",
    "81.63.0.0/16", "81.64.0.0/16", "81.65.0.0/16", "81.66.0.0/16",
    "81.67.0.0/16", "81.68.0.0/16", "81.69.0.0/16", "81.70.0.0/16",
    "81.71.0.0/16", "81.72.0.0/16", "81.73.0.0/16", "81.74.0.0/16",
    "81.75.0.0/16", "81.76.0.0/16", "81.77.0.0/16", "81.78.0.0/16",
    "81.79.0.0/16", "81.80.0.0/16", "81.81.0.0/16", "81.82.0.0/16",
    "81.83.0.0/16", "81.84.0.0/16", "81.85.0.0/16", "81.86.0.0/16",
    "81.87.0.0/16", "81.88.0.0/16", "81.89.0.0/16", "81.90.0.0/16",
    "81.91.0.0/16", "81.92.0.0/16", "81.93.0.0/16", "81.94.0.0/16",
    "81.95.0.0/16", "81.96.0.0/16", "81.97.0.0/16", "81.98.0.0/16",
    "81.99.0.0/16", "81.100.0.0/16", "81.101.0.0/16", "81.102.0.0/16",
    "81.103.0.0/16", "81.104.0.0/16", "81.105.0.0/16", "81.106.0.0/16",
    "81.107.0.0/16", "81.108.0.0/16", "81.109.0.0/16", "81.110.0.0/16",
    "81.111.0.0/16", "81.112.0.0/16", "81.113.0.0/16", "81.114.0.0/16",
    "81.115.0.0/16", "81.116.0.0/16", "81.117.0.0/16", "81.118.0.0/16",
    "81.119.0.0/16", "81.120.0.0/16", "81.121.0.0/16", "81.122.0.0/16",
    "81.123.0.0/16", "81.124.0.0/16", "81.125.0.0/16", "81.126.0.0/16",
    "81.127.0.0/16", "81.128.0.0/16", "81.129.0.0/16", "81.130.0.0/16",
    "81.131.0.0/16", "81.132.0.0/16", "81.133.0.0/16", "81.134.0.0/16",
    "81.135.0.0/16", "81.136.0.0/16", "81.137.0.0/16", "81.138.0.0/16",
    "81.139.0.0/16", "81.140.0.0/16", "81.141.0.0/16", "81.142.0.0/16",
    "81.143.0.0/16", "81.144.0.0/16", "81.145.0.0/16", "81.146.0.0/16",
    "81.147.0.0/16", "81.148.0.0/16", "81.149.0.0/16", "81.150.0.0/16",
    "81.151.0.0/16", "81.152.0.0/16", "81.153.0.0/16", "81.154.0.0/16",
    "81.155.0.0/16", "81.156.0.0/16", "81.157.0.0/16", "81.158.0.0/16",
    "81.159.0.0/16", "81.160.0.0/16", "81.161.0.0/16", "81.162.0.0/16",
    "81.163.0.0/16", "81.164.0.0/16", "81.165.0.0/16", "81.166.0.0/16",
    "81.167.0.0/16", "81.168.0.0/16", "81.169.0.0/16", "81.170.0.0/16",
    "81.171.0.0/16", "81.172.0.0/16", "81.173.0.0/16", "81.174.0.0/16",
    "81.175.0.0/16", "81.176.0.0/16", "81.177.0.0/16", "81.178.0.0/16",
    "81.179.0.0/16", "81.180.0.0/16", "81.181.0.0/16", "81.182.0.0/16",
    "81.183.0.0/16", "81.184.0.0/16", "81.185.0.0/16", "81.186.0.0/16",
    "81.187.0.0/16", "81.188.0.0/16", "81.189.0.0/16", "81.190.0.0/16",
    "81.191.0.0/16", "81.192.0.0/16", "81.193.0.0/16", "81.194.0.0/16",
    "81.195.0.0/16", "81.196.0.0/16", "81.197.0.0/16", "81.198.0.0/16",
    "81.199.0.0/16", "81.200.0.0/16", "81.201.0.0/16", "81.202.0.0/16",
    "81.203.0.0/16", "81.204.0.0/16", "81.205.0.0/16", "81.206.0.0/16",
    "81.207.0.0/16", "81.208.0.0/16", "81.209.0.0/16", "81.210.0.0/16",
    "81.211.0.0/16", "81.212.0.0/16", "81.213.0.0/16", "81.214.0.0/16",
    "81.215.0.0/16", "81.216.0.0/16", "81.217.0.0/16", "81.218.0.0/16",
    "81.219.0.0/16", "81.220.0.0/16", "81.221.0.0/16", "81.222.0.0/16",
    "81.223.0.0/16", "81.224.0.0/16", "81.225.0.0/16", "81.226.0.0/16",
    "81.227.0.0/16", "81.228.0.0/16", "81.229.0.0/16", "81.230.0.0/16",
    "81.231.0.0/16", "81.232.0.0/16", "81.233.0.0/16", "81.234.0.0/16",
    "81.235.0.0/16", "81.236.0.0/16", "81.237.0.0/16", "81.238.0.0/16",
    "81.239.0.0/16", "81.240.0.0/16", "81.241.0.0/16", "81.242.0.0/16",
    "81.243.0.0/16", "81.244.0.0/16", "81.245.0.0/16", "81.246.0.0/16",
    "81.247.0.0/16", "81.248.0.0/16", "81.249.0.0/16", "81.250.0.0/16",
    "81.251.0.0/16", "81.252.0.0/16", "81.253.0.0/16", "81.254.0.0/16",
    "81.255.0.0/16", "82.99.0.0/16", "82.100.0.0/16", "82.101.0.0/16",
    "82.102.0.0/16", "82.103.0.0/16", "82.104.0.0/16", "82.105.0.0/16",
    "82.106.0.0/16", "82.107.0.0/16", "82.108.0.0/16", "82.109.0.0/16",
    "82.110.0.0/16", "82.111.0.0/16", "82.112.0.0/16", "82.113.0.0/16",
    "82.114.0.0/16", "82.115.0.0/16", "82.116.0.0/16", "82.117.0.0/16",
    "82.118.0.0/16", "82.119.0.0/16", "82.120.0.0/16", "82.121.0.0/16",
    "82.122.0.0/16", "82.123.0.0/16", "82.124.0.0/16", "82.125.0.0/16",
    "82.126.0.0/16", "82.127.0.0/16", "82.128.0.0/16", "82.129.0.0/16",
    "82.130.0.0/16", "82.131.0.0/16", "82.132.0.0/16", "82.133.0.0/16",
    "82.134.0.0/16", "82.135.0.0/16", "82.136.0.0/16", "82.137.0.0/16",
    "82.138.0.0/16", "82.139.0.0/16", "82.140.0.0/16", "82.141.0.0/16",
    "82.142.0.0/16", "82.143.0.0/16", "82.144.0.0/16", "82.145.0.0/16",
    "82.146.0.0/16", "82.147.0.0/16", "82.148.0.0/16", "82.149.0.0/16",
    "82.150.0.0/16", "82.151.0.0/16", "82.152.0.0/16", "82.153.0.0/16",
    "82.154.0.0/16", "82.155.0.0/16", "82.156.0.0/16", "82.157.0.0/16",
    "82.158.0.0/16", "82.159.0.0/16", "82.160.0.0/16", "82.161.0.0/16",
    "82.162.0.0/16", "82.163.0.0/16", "82.164.0.0/16", "82.165.0.0/16",
    "82.166.0.0/16", "82.167.0.0/16", "82.168.0.0/16", "82.169.0.0/16",
    "82.170.0.0/16", "82.171.0.0/16", "82.172.0.0/16", "82.173.0.0/16",
    "82.174.0.0/16", "82.175.0.0/16", "82.176.0.0/16", "82.177.0.0/16",
    "82.178.0.0/16", "82.179.0.0/16", "82.180.0.0/16", "82.181.0.0/16",
    "82.182.0.0/16", "82.183.0.0/16", "82.184.0.0/16", "82.185.0.0/16",
    "82.186.0.0/16", "82.187.0.0/16", "82.188.0.0/16", "82.189.0.0/16",
    "82.190.0.0/16", "82.191.0.0/16", "82.192.0.0/16", "82.193.0.0/16",
    "82.194.0.0/16", "82.195.0.0/16", "82.196.0.0/16", "82.197.0.0/16",
    "82.198.0.0/16", "82.199.0.0/16", "82.200.0.0/16", "82.201.0.0/16",
    "82.202.0.0/16", "82.203.0.0/16", "82.204.0.0/16", "82.205.0.0/16",
    "82.206.0.0/16", "82.207.0.0/16", "82.208.0.0/16", "82.209.0.0/16",
    "82.210.0.0/16", "82.211.0.0/16", "82.212.0.0/16", "82.213.0.0/16",
    "82.214.0.0/16", "82.215.0.0/16", "82.216.0.0/16", "82.217.0.0/16",
    "82.218.0.0/16", "82.219.0.0/16", "82.220.0.0/16", "82.221.0.0/16",
    "82.222.0.0/16", "82.223.0.0/16", "82.224.0.0/16", "82.225.0.0/16",
    "82.226.0.0/16", "82.227.0.0/16", "82.228.0.0/16", "82.229.0.0/16",
    "82.230.0.0/16", "82.231.0.0/16", "82.232.0.0/16", "82.233.0.0/16",
    "82.234.0.0/16", "82.235.0.0/16", "82.236.0.0/16", "82.237.0.0/16",
    "82.238.0.0/16", "82.239.0.0/16", "82.240.0.0/16", "82.241.0.0/16",
    "82.242.0.0/16", "82.243.0.0/16", "82.244.0.0/16", "82.245.0.0/16",
    "82.246.0.0/16", "82.247.0.0/16", "82.248.0.0/16", "82.249.0.0/16",
    "82.250.0.0/16", "82.251.0.0/16", "82.252.0.0/16", "82.253.0.0/16",
    "82.254.0.0/16", "82.255.0.0/16",
]))

LAN_IPS = [
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    "127.0.0.0/8", "169.254.0.0/16",
    "::1/128", "fc00::/7", "fe80::/10",
]

SUPPORTED_PROTOCOLS = {
    "vmess", "vless", "trojan", "ss", "hysteria2", "hy2",
    "socks", "socks5", "http", "https", "wireguard", "wg",
    "tuic", "shadowtls", "naive+https", "naive+quic",
    "dnstt", "ssh", "psiphon", "tor",
}


def is_admin() -> bool:
    try:
        if os.name == "nt":
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        return os.geteuid() == 0
    except Exception as e:
        logging.debug("is_admin failed: %s", e)
        return False


def _is_unix() -> bool:
    return hasattr(os, "geteuid")


class Settings:
    _data = dict(DEFAULT_SETTINGS)
    _lock = threading.RLock()

    @classmethod
    def load(cls):
        with cls._lock:
            if SETTINGS_FILE.exists():
                try:
                    loaded = json.loads(SETTINGS_FILE.read_text())
                    cls._data.update(loaded)
                except Exception as e:
                    logging.warning("Settings.load failed: %s", e)

    @classmethod
    def save(cls):
        with cls._lock:
            tmp = SETTINGS_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(cls._data, indent=2))
            os.replace(tmp, SETTINGS_FILE)

    @classmethod
    def get(cls, key, default=None):
        with cls._lock:
            return cls._data.get(key, default)

    @classmethod
    def set(cls, key, value):
        with cls._lock:
            cls._data[key] = value
            cls.save()


_audit_lock = threading.Lock()


def audit(action: str, detail: str = ""):
    if not Settings.get("audit_enabled", True):
        return
    try:
        with _audit_lock:
            with open(AUDIT_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} | {action} | {detail}\n")
    except OSError:
        pass


class Sys:
    @staticmethod
    def _run(args: List[str], timeout: int = 10) -> bool:
        try:
            subprocess.run(args, capture_output=True, timeout=timeout)
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    @staticmethod
    def _ps(script: str, timeout: int = 15) -> bool:
        if PLATFORM["os"] != "windows":
            return False
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 script], capture_output=True, timeout=timeout)
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    @staticmethod
    def tts(text: str):
        if not Settings.get("tts", True):
            return
        clean = re.sub(r"[^\w\s\.\,]", " ", text)[:200]
        if TERMUX and Sys._run(["termux-tts-speak", clean]):
            return
        if PLATFORM["os"] == "windows":
            esc = clean.replace("'", "''")
            if Sys._ps(
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    f"$s.Speak('{esc}')"):
                return
        if shutil.which("espeak"):
            Sys._run(["espeak", clean])
        elif shutil.which("say"):
            Sys._run(["say", clean])
        elif shutil.which("spd-say"):
            Sys._run(["spd-say", clean])

    @staticmethod
    def notify(title: str, content: str = ""):
        if not Settings.get("notify", True):
            return
        if TERMUX:
            Sys._run(["termux-notification", "--title", title,
                     "--content", content, "--priority", "high"])
        elif PLATFORM["os"] == "windows":
            t = title.replace("'", "''")
            c = content.replace("'", "''")
            Sys._ps(
                "Add-Type -AssemblyName System.Windows.Forms; "
                "Add-Type -AssemblyName System.Drawing; "
                "$n = New-Object System.Windows.Forms.NotifyIcon; "
                "$n.Icon = [System.Drawing.SystemIcons]::Information; "
                "$n.Visible = $true; "
                f"$n.ShowBalloonTip(5000, '{t}', '{c}', "
                "[System.Windows.Forms.ToolTipIcon]::Info); "
                "Start-Sleep -Seconds 6; $n.Dispose()", timeout=20)
        elif shutil.which("notify-send"):
            Sys._run(["notify-send", title, content])
        elif PLATFORM["os"] == "macos":
            t = title.replace('"', '\\"')
            c = content.replace('"', '\\"')
            Sys._run(["osascript", "-e",
                      f'display notification "{c}" with title "{t}"'])
        logging.info(f"NOTIFY {title}: {content}")

    @staticmethod
    def vibrate(ms: int = 300):
        if not Settings.get("vibrate", True) or not TERMUX:
            return
        Sys._run(["termux-vibrate", "-d", str(ms)])

    @staticmethod
    def toast(text: str):
        if TERMUX:
            Sys._run(["termux-toast", text])
        elif PLATFORM["os"] == "windows":
            Sys.notify("MultiProxy", text)
        elif shutil.which("notify-send"):
            Sys._run(["notify-send", "MultiProxy", text])

    @staticmethod
    def torch(on: bool = True, duration_ms: int = 1000):
        if not TERMUX:
            return
        if not Settings.get("torch_on_connect", False) and on:
            return
        Sys._run(["termux-torch", "on" if on else "off"])
        if on and duration_ms > 0:
            threading.Timer(duration_ms / 1000.0,
                            lambda: Sys._run(["termux-torch", "off"])).start()

    @staticmethod
    def battery() -> Dict[str, Any]:
        if TERMUX:
            try:
                r = subprocess.run(["termux-battery-status"],
                                   capture_output=True, text=True, timeout=5)
                if r.returncode == 0:
                    return json.loads(r.stdout)
            except Exception as e:
                logging.debug("battery (termux) failed: %s", e)
            return {"percentage": 100, "plugged": "UNKNOWN"}
        os_name = PLATFORM["os"]
        if os_name == "windows":
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive",
                     "-Command",
                     "$b = Get-CimInstance Win32_Battery; "
                     "if ($b) { \"$($b.EstimatedChargeRemaining)|"
                     "$($b.BatteryStatus)\" } else { '100|2' }"],
                    capture_output=True, text=True, timeout=10)
                if r.returncode == 0 and "|" in r.stdout:
                    pct, st = r.stdout.strip().split("|", 1)
                    return {"percentage": int(float(pct)),
                            "plugged": "PLUGGED_AC" if st.strip() == "2"
                            else "DISCHARGING"}
            except Exception as e:
                logging.debug("battery (windows) failed: %s", e)
            return {"percentage": 100, "plugged": "PLUGGED_AC"}
        if os_name == "macos":
            try:
                r = subprocess.run(["pmset", "-g", "batt"],
                                   capture_output=True, text=True, timeout=5)
                m = re.search(r"(\d+)%", r.stdout)
                if m:
                    ac = "AC Power" in r.stdout
                    return {"percentage": int(m.group(1)),
                            "plugged": "PLUGGED_AC" if ac else "DISCHARGING"}
            except Exception as e:
                logging.debug("battery (macos) failed: %s", e)
            return {"percentage": 100, "plugged": "UNKNOWN"}
        try:
            for supply in Path("/sys/class/power_supply").iterdir():
                if not supply.name.lower().startswith("bat"):
                    continue
                pct = (supply / "capacity").read_text().strip()
                status = (supply / "status").read_text().strip().lower()
                return {"percentage": int(float(pct)),
                        "plugged": "PLUGGED_AC"
                        if status in ("charging", "full", "not charging")
                        else "DISCHARGING"}
        except Exception as e:
            logging.debug("battery (sysfs) failed: %s", e)
        if shutil.which("upower"):
            try:
                r = subprocess.run(["upower", "--dump"],
                                   capture_output=True, text=True, timeout=5)
                m = re.search(r"percentage:\s+(\d+)", r.stdout)
                state = re.search(r"state:\s+(\S+)", r.stdout)
                if m:
                    st = (state.group(1) if state else "").lower()
                    return {"percentage": int(m.group(1)),
                            "plugged": "PLUGGED_AC"
                            if st in ("charging", "fully-charged")
                            else "DISCHARGING"}
            except Exception as e:
                    logging.debug("battery (upower) failed: %s", e)
        return {"percentage": 100, "plugged": "UNKNOWN"}

    @staticmethod
    def clipboard_get() -> str:
        if TERMUX:
            try:
                r = subprocess.run(["termux-clipboard-get"],
                                   capture_output=True, text=True, timeout=3)
                return r.stdout if r.returncode == 0 else ""
            except Exception as e:
                logging.debug("clipboard_get (termux) failed: %s", e)
                return ""
        os_name = PLATFORM["os"]
        if os_name == "windows":
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive",
                     "-Command", "Get-Clipboard"],
                    capture_output=True, text=True, timeout=5)
                return r.stdout if r.returncode == 0 else ""
            except Exception as e:
                logging.debug("clipboard_get (windows) failed: %s", e)
                return ""
        if os_name == "macos":
            try:
                r = subprocess.run(["pbpaste"], capture_output=True,
                                   text=True, timeout=3)
                return r.stdout if r.returncode == 0 else ""
            except Exception as e:
                logging.debug("clipboard_get (macos) failed: %s", e)
                return ""
        for cmd in (["wl-paste"], ["xclip", "-selection", "clipboard", "-o"]):
            if shutil.which(cmd[0]):
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True,
                                       timeout=3)
                    if r.returncode == 0:
                        return r.stdout
                except Exception as e:
                    logging.debug("clipboard_get (%s) failed: %s", cmd[0], e)
        return ""

    @staticmethod
    def clipboard_set(text: str) -> bool:
        if TERMUX:
            return Sys._run(["termux-clipboard-set", text])
        os_name = PLATFORM["os"]
        if os_name == "windows":
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive",
                     "-Command", "Set-Clipboard", "-Value", text],
                    capture_output=True, timeout=5)
                return r.returncode == 0
            except Exception as e:
                logging.debug("clipboard_set (windows) failed: %s", e)
                return False
        if os_name == "macos":
            try:
                r = subprocess.run(["pbcopy"], input=text, text=True,
                                   timeout=3)
                return r.returncode == 0
            except Exception as e:
                logging.debug("clipboard_set (macos) failed: %s", e)
                return False
        for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"]):
            if shutil.which(cmd[0]):
                try:
                    r = subprocess.run(cmd, input=text, text=True, timeout=3)
                    if r.returncode == 0:
                        return True
                except Exception as e:
                    logging.debug("clipboard_set (%s) failed: %s", cmd[0], e)
        return False

    @staticmethod
    def flush_dns() -> bool:
        os_name = PLATFORM["os"]
        if os_name == "windows":
            return Sys._run(["ipconfig", "/flushdns"])
        if os_name == "macos":
            ok = Sys._run(["dscacheutil", "-flushcache"])
            return Sys._run(["killall", "-HUP", "mDNSResponder"]) and ok
        if shutil.which("resolvectl"):
            return Sys._run(["resolvectl", "flush-caches"])
        if shutil.which("systemd-resolve"):
            return Sys._run(["systemd-resolve", "--flush-caches"])
        return False

    @staticmethod
    def setup_storage() -> bool:
        if not TERMUX:
            return False
        return Sys._run(["termux-setup-storage"], timeout=30)


def battery_ok() -> bool:
    if not Settings.get("battery_aware", False) or not TERMUX:
        return True
    bat = Sys.battery()
    pct = bat.get("percentage", 100)
    plugged = bat.get("plugged", "")
    return pct > Settings.get("battery_threshold", 20) or "PLUGGED" in plugged


def screen_off_mode() -> bool:
    if not Settings.get("screen_off_aware", False) or not TERMUX:
        return False
    bat = Sys.battery()
    return "PLUGGED" not in bat.get("plugged", "")


class DependencyManager:
    XRAY_RELEASES = "https://api.github.com/repos/XTLS/Xray-core/releases/latest"
    HYSTERIA_RELEASES = "https://api.github.com/repos/apernet/hysteria/releases/latest"
    SINGBOX_RELEASES = "https://api.github.com/repos/SagerNet/sing-box/releases/latest"
    # The psiphon-tunnel-core-binaries repo has NO GitHub releases: binaries are
    # published as plain files in OS subdirectories of the master branch.
    PSIPHON_BINARIES_API = "https://api.github.com/repos/Psiphon-Labs/psiphon-tunnel-core-binaries/contents"
    PSIPHON_BINARIES_RAW = "https://raw.githubusercontent.com/Psiphon-Labs/psiphon-tunnel-core-binaries/master"
    PSIPHON_SOURCE_TARBALL = "https://codeload.github.com/Psiphon-Labs/psiphon-tunnel-core/tar.gz/refs/heads/master"
    # dnstt has no GitHub repo (codeload 404s). Official source is the dated
    # snapshot zip on bamsoftware.com; repo.or.cz gitweb mirror as fallback.
    DNSTT_SOURCE_PAGE = "https://www.bamsoftware.com/software/dnstt/"
    DNSTT_SOURCE_FALLBACKS = (
        "https://www.bamsoftware.com/software/dnstt/dnstt-20260501.zip",
        "https://repo.or.cz/dnstt.git/snapshot/refs/heads/master.tar.gz",
    )
    # tor-expert-bundle moved into per-version dirs on dist.torproject.org
    # (the old /win/tor-expert-bundle.zip path is gone). Versions are scraped
    # from the index at runtime; these are known-good fallbacks.
    TOR_DIST_INDEX = "https://dist.torproject.org/torbrowser/"
    TOR_VERSION_FALLBACKS = ("15.0.26", "15.0.25", "15.0.20")
    GEO_URLS = {
        "geoip.dat": "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat",
        "geosite.dat": "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat",
    }

    @classmethod
    def ensure_python_packages(cls):
        global _HAS_QR
        try:
            import qrcode  # noqa
            return
        except ImportError:
            pass
        console.print("[info]Installing qrcode...[/info]")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "qrcode[pil]"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            import importlib
            importlib.invalidate_caches()
            try:
                import qrcode  # noqa
                _HAS_QR = True
                console.print("[success]qrcode installed.[/success]")
            except ImportError:
                console.print(
                    "[warn]qrcode install reported success but import fails.[/warn]")
        except Exception as e:
            console.print(
                f"[warn]qrcode install failed: {rich_escape(str(e))}[/warn]")

    @classmethod
    def _run_pkg(cls, cmd: List[str], timeout: int = 600) -> bool:
        try:
            r = subprocess.run(cmd, capture_output=True,
                               text=True, timeout=timeout)
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    @classmethod
    def ensure_system_packages(cls):
        if PLATFORM["os"] == "windows":
            # Windows: nothing to pkg-install; winget/choco optional helpers.
            return
        if TERMUX:
            cls._run_pkg(["pkg", "update", "-y"], timeout=300)
            pkg_map = {
                "python": "python",
                "termux-api": None,
                "tor": "tor",
                "unzip": "unzip",
                "wget": "wget",
                "curl": "curl",
                "openssh": "ssh",
            }
            for pkg, binary in pkg_map.items():
                if binary is None:
                    if Path(TERMUX_PREFIX).joinpath("bin/termux-notification").exists():
                        continue
                elif shutil.which(binary):
                    continue
                console.print(f"[dim]pkg install {pkg} ...[/dim]")
                cls._run_pkg(["pkg", "install", "-y", pkg], timeout=600)
        elif PLATFORM["os"] == "linux":
            if shutil.which("apt-get"):
                if is_admin():
                    cls._run_pkg(["apt-get", "update", "-y"], timeout=300)
                pkgs = {"python3": "python3", "python3-pip": "pip3",
                        "curl": "curl", "unzip": "unzip", "tor": "tor",
                        "openssh-client": "ssh"}
                for pkg, binary in pkgs.items():
                    if shutil.which(binary):
                        continue
                    cmd = (["sudo", "-n", "apt-get", "install", "-y", pkg]
                           if not is_admin() and shutil.which("sudo")
                           else ["apt-get", "install", "-y", pkg])
                    cls._run_pkg(cmd, timeout=600)
            elif shutil.which("dnf"):
                pkgs = {"python3": "python3", "python3-pip": "pip3",
                        "curl": "curl", "unzip": "unzip", "tor": "tor",
                        "openssh-clients": "ssh"}
                for pkg, binary in pkgs.items():
                    if shutil.which(binary):
                        continue
                    cmd = (["sudo", "-n", "dnf", "install", "-y", pkg]
                           if not is_admin() and shutil.which("sudo")
                           else ["dnf", "install", "-y", pkg])
                    cls._run_pkg(cmd, timeout=600)
            elif shutil.which("pacman"):
                pkgs = {"python": "python", "python-pip": "pip",
                        "curl": "curl", "unzip": "unzip", "tor": "tor",
                        "openssh": "ssh"}
                for pkg, binary in pkgs.items():
                    if shutil.which(binary):
                        continue
                    cmd = (["sudo", "-n", "pacman", "-S", "--noconfirm", pkg]
                           if not is_admin() and shutil.which("sudo")
                           else ["pacman", "-S", "--noconfirm", pkg])
                    cls._run_pkg(cmd, timeout=600)
            elif shutil.which("apk"):
                pkgs = {"python3": "python3", "py3-pip": "pip3",
                        "curl": "curl", "unzip": "unzip", "tor": "tor",
                        "openssh-client": "ssh"}
                for pkg, binary in pkgs.items():
                    if shutil.which(binary):
                        continue
                    cls._run_pkg(["apk", "add", pkg], timeout=600)
        elif PLATFORM["os"] == "macos":
            if shutil.which("brew"):
                for pkg, binary in {"python": "python3", "tor": "tor",
                                    "curl": "curl", "unzip": "unzip"}.items():
                    if shutil.which(binary):
                        continue
                    cls._run_pkg(["brew", "install", pkg], timeout=900)

    @classmethod
    def _gh_latest_asset(cls, api_url: str, pattern: str) -> Optional[str]:
        try:
            req = urllib.request.Request(
                api_url, headers={"User-Agent": f"MPS/{VERSION}"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
            for asset in data.get("assets", []):
                if re.search(pattern, asset.get("name", ""), re.IGNORECASE):
                    return asset.get("browser_download_url")
        except urllib.error.HTTPError as e:
            if e.code == 403:
                console.print("[warn]GitHub API rate limit hit (403). "
                              "Wait an hour or set GITHUB_TOKEN.[/warn]")
            else:
                logging.warning(f"GitHub API error: {e}")
        except Exception as e:
            logging.warning(f"GitHub API error: {e}")
        return None

    @classmethod
    def _download_and_extract(cls, url: str, dest_dir: Path, binary_name: str) -> Optional[Path]:
        tmp = None
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            fname = url.split("/")[-1]
            tmp = dest_dir / ("download_" + fname)
            console.print(f"[dim]Downloading {fname}...[/dim]")
            req = urllib.request.Request(
                url, headers={"User-Agent": f"MPS/{VERSION}"})
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read(200 * 1024 * 1024)  # 200 MB cap
            tmp.write_bytes(data)
            payload = None
            if fname.endswith(".zip"):
                with zipfile.ZipFile(tmp, "r") as zf:
                    for name in zf.namelist():
                        if name.endswith("/"):
                            continue
                        base = name.rsplit("/", 1)[-1]
                        if base == binary_name or base == binary_name + ".exe":
                            payload = zf.read(name)
                            break
            elif fname.endswith((".tar.gz", ".tgz")):
                import tarfile
                with tarfile.open(tmp, "r:gz") as tf:
                    for m in tf.getmembers():
                        if m.isdir():
                            continue
                        base = m.name.rsplit("/", 1)[-1]
                        if base == binary_name or base == binary_name + ".exe":
                            f = tf.extractfile(m)
                            if f:
                                payload = f.read()
                            break
            else:
                # plain binary download
                if len(data) > 1000:
                    payload = data
            tmp.unlink(missing_ok=True)
            if payload:
                out = dest_dir / (binary_name + EXE_SUFFIX)
                out.write_bytes(payload)
                out.chmod(0o755)
                return out
            console.print(
                f"[warn]'{binary_name}' not found inside {fname}[/warn]")
            return None
        except Exception as e:
            console.print(
                f"[warn]Download failed: {rich_escape(str(e))}[/warn]")
            return None
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)

    @classmethod
    def _gh_contents_file(cls, subdir: str, names: List[str]) -> Optional[str]:
        """Find a file in a psiphon-tunnel-core-binaries subdirectory via the
        GitHub contents API. Returns its download_url, or None."""
        url = f"{cls.PSIPHON_BINARIES_API}/{subdir}"
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": f"MPS/{VERSION}"})
            with urllib.request.urlopen(req, timeout=30) as r:
                entries = json.loads(r.read().decode("utf-8", "replace"))
            if not isinstance(entries, list):
                return None
            for want in names:
                for e in entries:
                    if e.get("type") == "file" and e.get("name") == want:
                        return e.get("download_url")
        except Exception as exc:
            logging.warning("_gh_contents_file(%s) failed: %s", subdir, exc)
        return None

    @classmethod
    def _gh_api_raw_download(cls, subdir: str, name: str, dest_dir: Path,
                             binary_name: str) -> Optional[Path]:
        """Download a repo file through the GitHub contents API with a raw
        Accept header — fallback for when the raw CDN is unreachable."""
        url = f"{cls.PSIPHON_BINARIES_API}/{subdir}/{name}"
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            out = dest_dir / (binary_name + EXE_SUFFIX)
            console.print(f"[dim]Downloading {name} via GitHub API...[/dim]")
            req = urllib.request.Request(url, headers={
                "User-Agent": f"MPS/{VERSION}",
                "Accept": "application/vnd.github.raw"})
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
            if len(data) < 100_000:
                raise RuntimeError(f"Binary too small: {len(data)} bytes")
            out.write_bytes(data)
            out.chmod(0o755)
            return out
        except Exception as e:
            console.print(
                f"[warn]API download failed: {rich_escape(str(e))}[/warn]")
            return None

    @classmethod
    def _download_direct_binary(cls, url: str, dest_dir: Path, binary_name: str) -> Optional[Path]:
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            out = dest_dir / (binary_name + EXE_SUFFIX)
            console.print(f"[dim]Downloading {url.split('/')[-1]}...[/dim]")
            req = urllib.request.Request(
                url, headers={"User-Agent": f"MPS/{VERSION}"})
            with urllib.request.urlopen(req, timeout=180) as r:
                data = r.read()
            if len(data) < 100_000:
                raise RuntimeError(f"Binary too small: {len(data)} bytes")
            out.write_bytes(data)
            out.chmod(0o755)
            return out
        except Exception as e:
            console.print(
                f"[warn]Direct download failed: {rich_escape(str(e))}[/warn]")
            return None

    @classmethod
    def _build_psiphon_from_source(cls) -> Optional[Path]:
        """Last-resort fallback: build the console client from source with Go.
        Needed for platforms with no prebuilt binary (macOS, ARM Linux, Termux)."""
        go = shutil.which("go")
        if not go:
            console.print(
                "[dim]Go toolchain not found; skipping source build.[/dim]")
            return None
        console.print(
            "[info]Building psiphon-tunnel-core from source (Go)...[/info]")
        tmp = Path(tempfile.mkdtemp(prefix="mps_ptc_"))
        try:
            tar_path = tmp / "src.tar.gz"
            req = urllib.request.Request(cls.PSIPHON_SOURCE_TARBALL,
                                         headers={"User-Agent": f"MPS/{VERSION}"})
            with urllib.request.urlopen(req, timeout=300) as r:
                tar_path.write_bytes(r.read())
            import tarfile
            with tarfile.open(tar_path, "r:gz") as tf:
                tf.extractall(tmp)
            roots = [d for d in tmp.iterdir() if d.is_dir(
            ) and d.name.startswith("psiphon-tunnel-core-")]
            if not roots:
                return None
            cc = roots[0] / "ConsoleClient"
            if not cc.is_dir():
                return None
            env = dict(os.environ)
            if _platform.system() == "Darwin":
                env["CGO_ENABLED"] = "0"
            bin_name = "psiphon-tunnel-core" + EXE_SUFFIX
            subprocess.run([go, "build", "-o", bin_name, "."], cwd=cc,
                           env=env, check=True, timeout=1200)
            built = cc / bin_name
            if not built.is_file() or built.stat().st_size < 1_000_000:
                return None
            BIN_DIR.mkdir(parents=True, exist_ok=True)
            dest = BIN_DIR / bin_name
            shutil.move(str(built), str(dest))
            dest.chmod(0o755)
            return dest
        except Exception as e:
            console.print(
                f"[warn]Source build failed: {rich_escape(str(e))}[/warn]")
            return None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @classmethod
    def ensure_xray(cls, force: bool = False) -> Optional[str]:
        found = find_xray()
        if found and not force:
            return found
        if not Settings.get("auto_install", True):
            return None
        console.print("[info]Xray not found. Auto-installing...[/info]")
        arch = PLATFORM["arch"]
        os_id = PLATFORM["os"]
        if os_id == "windows":
            pat = r"Xray-windows-(64|arm64-v8a|32)\.zip"
        elif os_id == "macos":
            pat = r"Xray-macos-(64|arm64-v8a)\.zip"
        elif os_id == "android":
            pat = r"Xray-android-arm64-v8a\.zip" if arch == "aarch64" else r"Xray-android-armeabi-v7a\.zip"
        else:
            if arch == "aarch64":
                pat = r"Xray-linux-arm64-v8a\.zip"
            elif arch == "x86_64":
                pat = r"Xray-linux-64\.zip"
            elif arch == "armv7":
                pat = r"Xray-linux-arm32-v7a\.zip"
            else:
                pat = r"Xray-linux-64\.zip"
        url = cls._gh_latest_asset(cls.XRAY_RELEASES, pat)
        if not url:
            console.print(
                "[fail]Could not find Xray asset for this platform.[/fail]")
            return None
        path = cls._download_and_extract(url, BIN_DIR, "xray")
        if path:
            console.print(f"[success]Xray installed: {path}[/success]")
            cls.ensure_geo_files()
            return str(path)
        return None

    @classmethod
    def ensure_psiphon(cls, force: bool = False) -> Optional[str]:
        found = find_psiphon()
        if found and not force:
            console.print(f"[info]Psiphon already installed: {found}[/info]")
            return found
        if not Settings.get("auto_install", True):
            return None
        console.print("[info]Psiphon not found. Auto-installing...[/info]")
        arch = PLATFORM["arch"]
        os_id = PLATFORM["os"]

        # Prebuilt console binaries exist only for windows (i686, runs on x64
        # via WoW64) and linux (x86_64), in OS subdirectories of the repo tree.
        # macOS / Android / other arches have no prebuilt binary.
        subdir = None
        names: List[str] = []
        if os_id == "windows":
            subdir = "windows"
            names = ["psiphon-tunnel-core-x86_64.exe",   # future-proofing
                     "psiphon-tunnel-core-i686.exe"]     # only build published
        elif os_id == "linux" and arch == "x86_64":
            subdir = "linux"
            names = ["psiphon-tunnel-core-x86_64"]
        elif os_id == "linux" and arch == "i686":
            subdir = "linux"
            names = ["psiphon-tunnel-core-386", "psiphon-tunnel-core-x86_64"]

        path: Optional[Path] = None
        if subdir:
            url = cls._gh_contents_file(subdir, names)
            if url:
                console.print(
                    f"[dim]Found binary: {subdir}/{url.split('/')[-1]}[/dim]")
                path = cls._download_direct_binary(
                    url, BIN_DIR, "psiphon-tunnel-core")
            if not path:
                # Fallback 1: direct raw URLs (contents API may be unreachable).
                for name in names:
                    url = f"{cls.PSIPHON_BINARIES_RAW}/{subdir}/{name}"
                    console.print(f"[dim]Trying {subdir}/{name}...[/dim]")
                    path = cls._download_direct_binary(
                        url, BIN_DIR, "psiphon-tunnel-core")
                    if path:
                        break
            if not path:
                # Fallback 2: GitHub API raw download (raw CDN may be blocked).
                for name in names:
                    path = cls._gh_api_raw_download(
                        subdir, name, BIN_DIR, "psiphon-tunnel-core")
                    if path:
                        break

        if not path:
            path = cls._build_psiphon_from_source()

        if path:
            console.print(f"[success]Psiphon installed: {path}[/success]")
            return str(path)

        console.print("[warn]Automatic Psiphon install failed.[/warn]")
        console.print(
            "[warn]Prebuilt binaries exist only for Windows (i686) and Linux (x86_64).[/warn]")
        if os_id == "windows":
            console.print("[dim]curl -L -o psiphon-tunnel-core.exe \\[/dim]")
            console.print(
                f"[dim]  {cls.PSIPHON_BINARIES_RAW}/windows/psiphon-tunnel-core-i686.exe[/dim]")
        elif os_id == "linux" and arch == "x86_64":
            console.print("[dim]wget -O ~/psiphon-tunnel-core \\[/dim]")
            console.print(
                f"[dim]  {cls.PSIPHON_BINARIES_RAW}/linux/psiphon-tunnel-core-x86_64[/dim]")
            console.print("[dim]chmod +x ~/psiphon-tunnel-core[/dim]")
        else:
            console.print(
                "[warn]No prebuilt binary for this platform; build from source:[/warn]")
            console.print(
                "[dim]git clone https://github.com/Psiphon-Labs/psiphon-tunnel-core.git[/dim]")
            console.print(
                "[dim]cd psiphon-tunnel-core/ConsoleClient && go build -o psiphon-tunnel-core .[/dim]")
        return None

    @classmethod
    def ensure_geo_files(cls, force: bool = False) -> bool:
        GEO_DIR.mkdir(exist_ok=True)
        ok = True
        MIN_SIZES = {"geoip.dat": 8_000_000, "geosite.dat": 10_000_000}
        for name, url in cls.GEO_URLS.items():
            dest = GEO_DIR / name
            need_download = force
            if not dest.exists():
                need_download = True
            elif dest.stat().st_size < MIN_SIZES.get(name, 1_000_000):
                console.print(
                    f"[warn]{name} is too small ({dest.stat().st_size} bytes) — "
                    f"likely truncated, re-downloading[/warn]")
                need_download = True
            if need_download:
                console.print(f"[info]Downloading {name}...[/info]")
                try:
                    req = urllib.request.Request(
                        url, headers={"User-Agent": f"MPS/{VERSION}"})
                    with urllib.request.urlopen(req, timeout=180) as r:
                        data = r.read()
                    if len(data) < MIN_SIZES.get(name, 100_000):
                        raise RuntimeError(
                            f"{name} too small ({len(data)} bytes, expected ≥ "
                            f"{MIN_SIZES.get(name, 100_000)})")
                    dest.write_bytes(data)
                    console.print(
                        f"[success]{name} → {dest.stat().st_size//1024} KB[/success]")
                except Exception as e:
                    console.print(
                        f"[fail]{name}: {rich_escape(str(e))}[/fail]")
                    ok = False
        xray = find_xray()
        if xray:
            bin_dir = Path(xray).resolve().parent
            for name in cls.GEO_URLS:
                src = GEO_DIR / name
                if src.exists():
                    try:
                        shutil.copy2(src, bin_dir / name)
                    except OSError:
                        pass
        return ok

    @classmethod
    def ensure_hysteria(cls, force: bool = False) -> Optional[str]:
        if not force:
            p = find_hysteria()
            if p:
                return p
        os_id, arch = PLATFORM["os"], PLATFORM["arch"]
        if TERMUX:
            if cls._run_pkg(["pkg", "install", "-y", "hysteria"], timeout=600):
                return find_hysteria()
            return None
        if os_id == "windows":
            asset = "hysteria-windows-amd64(-avx|-gcc)?\\.exe|hysteria-windows-amd64\\.exe"
        elif os_id == "linux":
            asset = f"hysteria-linux-{arch if arch != 'x86_64' else 'amd64'}(\\.avx)?$"
        elif os_id == "macos":
            asset = "hysteria-macos-(universal|amd64|arm64)"
        else:
            console.print(
                "[warn]No prebuilt Hysteria2 for this platform.[/warn]")
            return None
        url = cls._gh_latest_asset(cls.HYSTERIA_RELEASES, asset)
        if not url:
            console.print(
                "[warn]No matching Hysteria2 release asset found.[/warn]")
            return None
        p = cls._download_and_extract(url, BIN_DIR, "hysteria")
        if p:
            console.print(f"[success]Hysteria2 installed: {p}[/success]")
            return str(p)
        return None

    @classmethod
    def ensure_singbox(cls, force: bool = False) -> Optional[str]:
        if not force:
            p = find_singbox()
            if p:
                return p
        os_id, arch = PLATFORM["os"], PLATFORM["arch"]
        if TERMUX:
            if cls._run_pkg(["pkg", "install", "-y", "sing-box"], timeout=600):
                return find_singbox()
            return None
        if os_id == "windows":
            asset = r"sing-box-.*-windows-amd64.*\.zip"
        elif os_id == "linux":
            a = "amd64" if arch == "x86_64" else arch
            asset = rf"sing-box-.*-linux-{a}.*\.(zip|tar\.gz)"
        elif os_id == "macos":
            asset = r"sing-box-.*-macos-.*\.(zip|tar\.gz)"
        else:
            console.print(
                "[warn]No prebuilt sing-box for this platform.[/warn]")
            return None
        url = cls._gh_latest_asset(cls.SINGBOX_RELEASES, asset)
        if not url:
            console.print(
                "[warn]No matching sing-box release asset found.[/warn]")
            return None
        p = cls._download_and_extract(url, BIN_DIR, "sing-box")
        if p:
            console.print(f"[success]sing-box installed: {p}[/success]")
            return str(p)
        return None

    @classmethod
    def ensure_tor(cls, force: bool = False) -> Optional[str]:
        if not force:
            p = find_tor()
            if p:
                return p
        os_id = PLATFORM["os"]
        if TERMUX:
            if cls._run_pkg(["pkg", "install", "-y", "tor"], timeout=600):
                return find_tor()
            return None
        if os_id == "linux":
            if shutil.which("apt-get"):
                cmd = (["sudo", "-n", "apt-get", "install", "-y", "tor"]
                       if not is_admin() and shutil.which("sudo")
                       else ["apt-get", "install", "-y", "tor"])
            elif shutil.which("dnf"):
                cmd = (["sudo", "-n", "dnf", "install", "-y", "tor"]
                       if not is_admin() and shutil.which("sudo")
                       else ["dnf", "install", "-y", "tor"])
            elif shutil.which("pacman"):
                cmd = (["sudo", "-n", "pacman", "-S", "--noconfirm", "tor"]
                       if not is_admin() and shutil.which("sudo")
                       else ["pacman", "-S", "--noconfirm", "tor"])
            else:
                console.print(
                    "[warn]No supported package manager found for tor.[/warn]")
                return None
            if cls._run_pkg(cmd, timeout=900):
                return find_tor()
            return None
        if os_id == "macos":
            if shutil.which("brew"):
                if cls._run_pkg(["brew", "install", "tor"], timeout=900):
                    return find_tor()
            return None
        if os_id == "windows":
            p = cls._install_tor_windows()
            if p:
                console.print(f"[success]Tor installed: {p}[/success]")
                return str(p)
        return None

    @classmethod
    def _tor_candidate_urls(cls) -> List[str]:
        """Build tor-expert-bundle URLs for this platform, newest version first."""
        os_id, arch = PLATFORM["os"], PLATFORM["arch"]
        if os_id not in ("windows", "linux", "macos"):
            return []
        urls: List[str] = []
        versions: List[str] = []
        try:
            req = urllib.request.Request(cls.TOR_DIST_INDEX,
                                         headers={"User-Agent": f"MPS/{VERSION}"})
            with urllib.request.urlopen(req, timeout=30) as r:
                html = r.read(200_000).decode("utf-8", "ignore")
            versions = sorted(set(re.findall(r'href="(\d+\.\d+\.\d+)/"', html)),
                              key=lambda v: [int(x) for x in v.split(".")],
                              reverse=True)
        except Exception as e:
            logging.warning(f"tor dist index scrape failed: {e}")
        for v in list(versions[:3]) + [v for v in cls.TOR_VERSION_FALLBACKS
                                       if v not in versions[:3]]:
            urls.append(f"https://dist.torproject.org/torbrowser/{v}/"
                        f"tor-expert-bundle-{os_id}-{arch}-{v}.tar.gz")
        return urls

    @classmethod
    def _install_tor_windows(cls) -> Optional[Path]:
        for url in cls._tor_candidate_urls():
            p = cls._download_and_extract(url, BIN_DIR, "tor")
            if p:
                return p
        console.print("[warn]No tor-expert-bundle download worked. "
                      "Get it manually from https://www.torproject.org/download/tor/ "
                      "and place tor.exe in mps_data/bin/[/warn]")
        return None

    @classmethod
    def ensure_wg(cls, force: bool = False) -> Optional[str]:
        if not force:
            p = find_wg_quick()
            if p:
                return p
        os_id = PLATFORM["os"]
        if os_id == "windows":
            console.print("[warn]wg-quick is Linux-only. On Windows, install the "
                          "WireGuard GUI app (https://wireguard.com/install) — "
                          "it manages tunnels itself.[/warn]")
            return None
        if TERMUX:
            if cls._run_pkg(["pkg", "install", "-y", "wireguard-tools"], timeout=600):
                return find_wg_quick()
            return None
        if os_id == "linux":
            if shutil.which("apt-get"):
                pkg = "wireguard-tools"
                cmd = (["sudo", "-n", "apt-get", "install", "-y", pkg]
                       if not is_admin() and shutil.which("sudo")
                       else ["apt-get", "install", "-y", pkg])
            elif shutil.which("dnf"):
                pkg = "wireguard-tools"
                cmd = (["sudo", "-n", "dnf", "install", "-y", pkg]
                       if not is_admin() and shutil.which("sudo")
                       else ["dnf", "install", "-y", pkg])
            elif shutil.which("pacman"):
                pkg = "wireguard-tools"
                cmd = (["sudo", "-n", "pacman", "-S", "--noconfirm", pkg]
                       if not is_admin() and shutil.which("sudo")
                       else ["pacman", "-S", "--noconfirm", pkg])
            else:
                console.print(
                    "[warn]No supported package manager for wireguard-tools.[/warn]")
                return None
            if cls._run_pkg(cmd, timeout=900):
                return find_wg_quick()
        return None

    @classmethod
    def ensure_dnstt(cls, force: bool = False) -> Optional[str]:
        if not force:
            p = find_dnstt()
            if p:
                return p
        if not shutil.which("go"):
            console.print("[warn]dnstt-client has no official prebuilt binaries; "
                          "it must be built from source with Go.[/warn]")
            console.print(
                "[dim]Install Go: https://go.dev/dl/ then re-run this.[/dim]")
            return None
        console.print(
            "[info]Building dnstt-client from source (needs Go)...[/info]")
        urls = [cls.DNSTT_SOURCE_PAGE] + list(cls.DNSTT_SOURCE_FALLBACKS)
        for url in urls:
            try:
                with tempfile.TemporaryDirectory() as td:
                    tdp = Path(td)
                    if url == cls.DNSTT_SOURCE_PAGE:
                        # Scrape the download page for the newest snapshot zip.
                        req = urllib.request.Request(
                            url, headers={"User-Agent": f"MPS/{VERSION}"})
                        with urllib.request.urlopen(req, timeout=60) as r:
                            html = r.read(300_000).decode("utf-8", "ignore")
                        zips = re.findall(r'href="(dnstt-\d{8}\.zip)"', html)
                        if not zips:
                            console.print(
                                "[dim]No snapshot zip found on page; trying fallbacks...[/dim]")
                            continue
                        src_url = urllib.parse.urljoin(url, zips[0])
                    else:
                        src_url = url
                    console.print(
                        f"[dim]Fetching {src_url.rsplit('/', 1)[-1]}...[/dim]")
                    req = urllib.request.Request(
                        src_url, headers={"User-Agent": f"MPS/{VERSION}"})
                    with urllib.request.urlopen(req, timeout=120) as r:
                        blob = r.read(50 * 1024 * 1024)
                    src_root = tdp / "src"
                    src_root.mkdir()
                    if src_url.endswith(".zip"):
                        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                            zf.extractall(src_root)
                    else:
                        import tarfile
                        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
                            tf.extractall(src_root)
                    # Archive contains a single top-level dir (dnstt-<date>/).
                    entries = [e for e in src_root.iterdir() if e.is_dir()]
                    src_dir = entries[0] if len(entries) == 1 else src_root
                    if not (src_dir / "dnstt-client").is_dir():
                        console.print(
                            "[dim]Source layout unexpected; trying next URL...[/dim]")
                        continue
                    out = BIN_DIR / ("dnstt-client" + EXE_SUFFIX)
                    cmd = ["go", "build", "-o", str(out), "./dnstt-client"]
                    r = subprocess.run(cmd, cwd=str(src_dir), capture_output=True,
                                       text=True, timeout=600)
                    if r.returncode == 0 and out.exists():
                        out.chmod(0o755)
                        console.print(
                            f"[success]dnstt-client built: {out}[/success]")
                        return str(out)
                    console.print(
                        f"[warn]go build failed: {rich_escape(r.stderr[:300])}[/warn]")
            except Exception as e:
                console.print(f"[warn]dnstt source fetch failed ({url.rsplit('/', 1)[-1]}): "
                              f"{rich_escape(str(e))}[/warn]")
        return None

    @classmethod
    def ensure_all(cls):
        if not Settings.get("auto_install", True):
            console.print("[dim]Auto-install disabled in settings.[/dim]")
            return
        console.print(Rule("[title]🔧 Dependency Check[/title]"))
        cls.ensure_python_packages()
        cls.ensure_system_packages()
        cls.ensure_xray()
        cls.ensure_psiphon()
        cls.ensure_geo_files()
        console.print("[success]Dependency check complete.[/success]")


def _ensure_executable(path: str) -> str:
    try:
        st = os.stat(path)
        if not (st.st_mode & 0o111):
            os.chmod(path, 0o755)
            logging.info(f"chmod 755 applied to {path}")
    except OSError:
        pass
    return path


def find_xray() -> Optional[str]:
    candidates = []
    if TERMUX:
        p = Path(TERMUX_PREFIX) / "bin" / "xray"
        if p.exists():
            candidates.append(str(p))
    p = shutil.which("xray")
    if p:
        candidates.append(p)
    for d in (BIN_DIR, SCRIPT_DIR, SCRIPT_DIR/"bin", SCRIPT_DIR/"cores"):
        for n in ("xray", "xray.exe"):
            c = d / n
            if c.exists() and c.is_file():
                candidates.append(str(c))
    for path in candidates:
        return _ensure_executable(path)
    return None


def find_hysteria() -> Optional[str]:
    candidates = []
    if TERMUX:
        for n in ("hysteria", "hysteria2"):
            p = Path(TERMUX_PREFIX)/"bin"/n
            if p.exists():
                candidates.append(str(p))
    for n in ("hysteria", "hysteria2"):
        p = shutil.which(n)
        if p:
            candidates.append(p)
    for d in (BIN_DIR, SCRIPT_DIR, SCRIPT_DIR/"bin"):
        for n in ("hysteria", "hysteria2", "hysteria.exe", "hysteria2.exe"):
            c = d / n
            if c.exists() and c.is_file():
                candidates.append(str(c))
    for path in candidates:
        return _ensure_executable(path)
    return None


def find_wg_quick() -> Optional[str]:
    candidates = []
    if TERMUX:
        p = Path(TERMUX_PREFIX) / "bin" / "wg-quick"
        if p.exists():
            candidates.append(str(p))
    p = shutil.which("wg-quick")
    if p:
        candidates.append(p)
    for d in (BIN_DIR, SCRIPT_DIR, SCRIPT_DIR/"bin"):
        for n in ("wg-quick", "wg-quick.exe"):
            c = d / n
            if c.exists() and c.is_file():
                candidates.append(str(c))
    for path in candidates:
        return _ensure_executable(path)
    return None


def find_singbox() -> Optional[str]:
    candidates = []
    if TERMUX:
        p = Path(TERMUX_PREFIX)/"bin"/"sing-box"
        if p.exists():
            candidates.append(str(p))
    for n in ("sing-box", "singbox"):
        p = shutil.which(n)
        if p:
            candidates.append(p)
    for d in (BIN_DIR, SCRIPT_DIR, SCRIPT_DIR/"bin"):
        for n in ("sing-box", "sing-box.exe", "singbox", "singbox.exe"):
            c = d / n
            if c.exists() and c.is_file():
                candidates.append(str(c))
    for path in candidates:
        return _ensure_executable(path)
    return None


def find_dnstt() -> Optional[str]:
    candidates = []
    if TERMUX:
        p = Path(TERMUX_PREFIX) / "bin" / "dnstt-client"
        if p.exists():
            candidates.append(str(p))
    p = shutil.which("dnstt-client")
    if p:
        candidates.append(p)
    for d in (BIN_DIR, SCRIPT_DIR, SCRIPT_DIR/"bin"):
        for n in ("dnstt-client", "dnstt-client.exe"):
            c = d / n
            if c.exists() and c.is_file():
                candidates.append(str(c))
    for path in candidates:
        return _ensure_executable(path)
    return None


def find_psiphon() -> Optional[str]:
    candidates = []
    if TERMUX:
        p = Path(TERMUX_PREFIX) / "bin" / "psiphon-tunnel-core"
        if p.exists():
            candidates.append(str(p))
    for n in ("psiphon-tunnel-core", "brainfuck-psiphon-pro-go"):
        p = shutil.which(n)
        if p:
            candidates.append(p)
    for d in (BIN_DIR, SCRIPT_DIR, SCRIPT_DIR/"bin"):
        for n in ("psiphon-tunnel-core", "psiphon-tunnel-core.exe"):
            c = d / n
            if c.exists() and c.is_file():
                candidates.append(str(c))
    try:
        for n in ("psiphon-tunnel-core", "psiphon-tunnel-core.exe"):
            h = Path.home() / n
            if h.exists() and h.is_file():
                candidates.append(str(h))
    except Exception as e:
        logging.debug("find_psiphon home scan failed: %s", e)
    for path in candidates:
        return _ensure_executable(path)
    return None


def find_tor() -> Optional[str]:
    candidates = []
    if TERMUX:
        p = Path(TERMUX_PREFIX)/"bin"/"tor"
        if p.exists():
            candidates.append(str(p))
    p = shutil.which("tor")
    if p:
        candidates.append(p)
    for d in (BIN_DIR, SCRIPT_DIR, SCRIPT_DIR/"bin"):
        for n in ("tor", "tor.exe"):
            c = d / n
            if c.exists() and c.is_file():
                candidates.append(str(c))
    for path in candidates:
        return _ensure_executable(path)
    return None


class URLParser:
    @classmethod
    def parse(cls, link: str) -> Optional[Dict[str, Any]]:
        link = link.strip()
        if not link or link.startswith("#"):
            return None
        scheme = link.split("://", 1)[0].lower() if "://" in link else ""
        try:
            if scheme == "vmess":
                return cls._parse_vmess(link)
            if scheme == "vless":
                return cls._parse_vless(link)
            if scheme == "trojan":
                return cls._parse_trojan(link)
            if scheme == "ss":
                return cls._parse_ss(link)
            if scheme in ("hysteria2", "hy2"):
                return cls._parse_hysteria2(link)
            if scheme in ("socks", "socks5"):
                return cls._parse_socks(link)
            if scheme in ("wireguard", "wg"):
                return cls._parse_wireguard(link)
            if scheme == "tuic":
                return cls._parse_tuic(link)
            if scheme == "shadowtls":
                return cls._parse_shadowtls(link)
            if scheme in ("naive+https", "naive+quic"):
                return cls._parse_naive(link)
            if scheme == "dnstt":
                return cls._parse_dnstt(link)
            if scheme == "ssh":
                return cls._parse_ssh(link)
            if scheme == "psiphon":
                return cls._parse_psiphon(link)
            if scheme == "tor":
                return cls._parse_tor(link)
        except Exception as e:
            logging.debug(f"Parse error for {link[:50]}: {e}")
        return None

    @staticmethod
    def _b64(s: str) -> Optional[str]:
        try:
            s = s.strip().replace("-", "+").replace("_", "/")
            pad = "=" * (-len(s) % 4)
            return base64.b64decode(s + pad).decode("utf-8", errors="ignore")
        except Exception as e:
            logging.debug("_b64 decode failed: %s", e)
            return None

    @staticmethod
    def _url_parts(link: str):
        parsed = urllib.parse.urlparse(link)
        if not parsed.hostname:
            return None
        try:
            port = parsed.port or 443
        except ValueError:
            port = 443
        return {
            "scheme": parsed.scheme,
            "userinfo": parsed.username or "",
            "password": parsed.password or "",
            "host": parsed.hostname, "port": port,
            "params": dict(urllib.parse.parse_qsl(parsed.query)),
            "name": urllib.parse.unquote(parsed.fragment or ""),
        }

    @classmethod
    def _parse_vless(cls, link):
        p = cls._url_parts(link)
        if not p:
            return None
        q = p["params"]
        cfg = {
            "address": p["host"], "port": p["port"], "id": p["userinfo"],
            "encryption": q.get("encryption", "none"),
            "flow": q.get("flow", ""),
            "network": q.get("type", "tcp"), "security": q.get("security", "none"),
            "sni": q.get("sni") or q.get("host") or p["host"],
            "fp": q.get("fp", "chrome"),
            "path": urllib.parse.unquote(q.get("path", "/")),
            "host_header": q.get("host", ""),
            "serviceName": q.get("serviceName", ""),
            "alpn": [x for x in q.get("alpn", "").split(",") if x],
        }
        if cfg["security"] == "reality":
            cfg.update({"pbk": q.get("pbk", ""), "sid": q.get(
                "sid", ""), "spx": q.get("spx", "/")})
        return {"protocol": "vless", "name": p["name"] or f"vless-{p['host']}:{p['port']}", "config": cfg}

    @classmethod
    def _parse_vmess(cls, link):
        decoded = cls._b64(link[8:])
        if not decoded:
            return None
        try:
            obj = json.loads(decoded)
        except Exception as e:
            logging.debug("_parse_vmess failed: %s", e)
            return None
        cfg = {
            "address": obj.get("add", ""), "port": int(obj.get("port", 443)),
            "id": obj.get("id", ""), "alterId": int(obj.get("aid", 0) or 0),
            "security": obj.get("scy", "auto") or "auto",
            "network": obj.get("net", "tcp"),
            "security_type": obj.get("tls", ""),
            "sni": obj.get("sni") or obj.get("host") or obj.get("add", ""),
            "fp": obj.get("fp", "chrome"), "path": obj.get("path", "/"),
            "host_header": obj.get("host", ""),
            "serviceName": obj.get("path", "") if obj.get("net") == "grpc" else "",
            "alpn": [x for x in (obj.get("alpn") or "").split(",") if x],
        }
        if not cfg["address"]:
            return None
        return {"protocol": "vmess", "name": obj.get("ps") or f"vmess-{cfg['address']}:{cfg['port']}", "config": cfg}

    @classmethod
    def _parse_trojan(cls, link):
        p = cls._url_parts(link)
        if not p:
            return None
        q = p["params"]
        cfg = {
            "address": p["host"], "port": p["port"], "password": p["userinfo"],
            "sni": q.get("sni") or p["host"], "fp": q.get("fp", "chrome"),
            "network": q.get("type", "tcp"), "path": urllib.parse.unquote(q.get("path", "/")),
            "host_header": q.get("host", ""), "serviceName": q.get("serviceName", ""),
            "alpn": [x for x in q.get("alpn", "").split(",") if x],
            "allowInsecure": q.get("allowInsecure") == "1",
        }
        return {"protocol": "trojan", "name": p["name"] or f"trojan-{p['host']}:{p['port']}", "config": cfg}

    @classmethod
    def _parse_ss(cls, link):
        body = link[5:]
        name = ""
        if "#" in body:
            body, name = body.split("#", 1)
            name = urllib.parse.unquote(name)
        params = {}
        if "?" in body:
            body, qs = body.split("?", 1)
            params = dict(urllib.parse.parse_qsl(qs))
        method = password = host = None
        port = 8388
        if "@" in body:
            userinfo, hostport = body.rsplit("@", 1)
            if ":" in hostport:
                host, ps = hostport.rsplit(":", 1)
                port = int(ps)
            else:
                host = hostport
            if ":" in userinfo:
                method, password = userinfo.split(":", 1)
            else:
                d = cls._b64(userinfo)
                if d and ":" in d:
                    method, password = d.split(":", 1)
        else:
            d = cls._b64(body)
            if d and "@" in d:
                creds, hostport = d.rsplit("@", 1)
                if ":" in creds:
                    method, password = creds.split(":", 1)
                if ":" in hostport:
                    host, ps = hostport.rsplit(":", 1)
                    port = int(ps)
        if not all([method, password, host]):
            return None
        cfg = {"address": host, "port": port, "method": method,
               "password": password, "plugin": params.get("plugin", "")}
        return {"protocol": "ss", "name": name or f"ss-{host}:{port}", "config": cfg}

    @classmethod
    def _parse_hysteria2(cls, link):
        p = cls._url_parts(link)
        if not p:
            return None
        q = p["params"]
        cfg = {
            "address": p["host"], "port": p["port"],
            "password": p["userinfo"] or p["password"],
            "sni": q.get("sni") or p["host"],
            "insecure": q.get("insecure") == "1",
            "obfs": q.get("obfs", ""), "obfs_password": q.get("obfs-password", ""),
            "up_mbps": int(q.get("upmbps", 50) or 50), "down_mbps": int(q.get("downmbps", 50) or 50),
        }
        return {"protocol": "hysteria2", "name": p["name"] or f"hy2-{p['host']}:{p['port']}", "config": cfg}

    @classmethod
    def _parse_socks(cls, link):
        p = cls._url_parts(link)
        if not p:
            return None
        cfg = {"address": p["host"], "port": p["port"],
               "username": p["userinfo"], "password": p["password"]}
        return {"protocol": "socks", "name": p["name"] or f"socks-{p['host']}:{p['port']}", "config": cfg}

    @classmethod
    def _parse_wireguard(cls, link):
        p = cls._url_parts(link)
        if not p:
            return None
        q = p["params"]
        priv = urllib.parse.unquote(p["userinfo"])
        pub = q.get("publickey") or q.get("public_key") or ""
        if not priv or not pub:
            return None
        cfg = {
            "address": p["host"], "port": p["port"],
            "peer_endpoint_host": p["host"], "peer_endpoint_port": p["port"],
            "private_key": priv, "public_key": pub,
            "local_address": q.get("address", "10.0.0.2/32"),
            "allowed_ips": q.get("allowedips", "0.0.0.0/0"),
            "dns": q.get("dns", "1.1.1.1"),
            "preshared_key": q.get("presharedkey", ""),
            "mtu": int(q.get("mtu", 1420) or 1420),
            "keepalive": int(q.get("keepalive", 25) or 25),
        }
        return {"protocol": "wireguard", "name": p["name"] or f"wg-{p['host']}:{p['port']}", "config": cfg}

    @classmethod
    def _parse_tuic(cls, link):
        p = cls._url_parts(link)
        if not p:
            return None
        q = p["params"]
        cfg = {
            "address": p["host"], "port": p["port"],
            "uuid": p["userinfo"], "password": p["password"],
            "sni": q.get("sni") or p["host"],
            "alpn": q.get("alpn", "h3").split(","),
            "congestion_control": q.get("congestion_control", "bbr"),
            "udp_relay_mode": q.get("udp_relay_mode", "native"),
            "allow_insecure": q.get("allow_insecure") == "1",
            "disable_sni": q.get("disable_sni") == "1",
        }
        return {"protocol": "tuic", "name": p["name"] or f"tuic-{p['host']}:{p['port']}", "config": cfg}

    @classmethod
    def _parse_shadowtls(cls, link):
        p = cls._url_parts(link)
        if not p:
            return None
        q = p["params"]
        cfg = {"address": p["host"], "port": p["port"],
               "password": p["userinfo"], "version": int(q.get("version", 3)),
               "sni": q.get("sni") or p["host"],
               "plugin": q.get("plugin", ""), "plugin_opts": q.get("plugin_opts", "")}
        return {"protocol": "shadowtls", "name": p["name"] or f"stls-{p['host']}:{p['port']}", "config": cfg}

    @classmethod
    def _parse_naive(cls, link):
        p = cls._url_parts(link)
        if not p:
            return None
        q = p["params"]
        cfg = {"address": p["host"], "port": p["port"],
               "username": p["userinfo"], "password": p["password"],
               "scheme": "https" if "quic" not in link.lower() else "quic",
               "padding": q.get("padding") == "true",
               "sni": q.get("sni") or p["host"],
               "insecure": q.get("insecure") == "1"}
        return {"protocol": "naive", "name": p["name"] or f"naive-{p['host']}:{p['port']}", "config": cfg}

    @classmethod
    def _parse_dnstt(cls, link):
        p = cls._url_parts(link)
        if not p:
            return None
        q = p["params"]
        cfg = {"domain": p["userinfo"] or q.get("domain", ""),
               "resolver": f"{p['host']}:{p['port']}",
               "pubkey": q.get("pubkey", ""),
               "socks_port": int(q.get("socks_port", 10808))}
        return {"protocol": "dnstt", "name": p["name"] or f"dnstt-{p['host']}", "config": cfg}

    @classmethod
    def _parse_ssh(cls, link):
        p = cls._url_parts(link)
        if not p:
            return None
        q = p["params"]
        cfg = {"address": p["host"], "port": p["port"] or 22,
               "username": p["userinfo"], "password": p["password"],
               "socks_port": int(q.get("socks_port", 10808)),
               "private_key_path": q.get("private_key", "")}
        return {"protocol": "ssh", "name": p["name"] or f"ssh-{p['host']}", "config": cfg}

    @classmethod
    def _parse_psiphon(cls, link):
        p = cls._url_parts(link)
        if not p:
            return None
        q = p["params"]
        cfg = {
            "region": q.get("region", ""),
            "config_url": q.get("config_url", ""),
            "local_socks_port": int(q.get("socks_port", Settings.get("socks_port", 10808))),
            "extra_args": q.get("args", ""),
        }
        return {"protocol": "psiphon", "name": p["name"] or "psiphon", "config": cfg}

    @classmethod
    def _parse_tor(cls, link):
        p = cls._url_parts(link)
        if not p:
            return {"protocol": "tor", "name": "tor-default",
                    "config": {"bridges": [], "socks_port": 9050}}
        q = p["params"]
        bridges = [b.strip()
                   for b in (q.get("bridges", "") or "").split(";") if b.strip()]
        cfg = {"bridges": bridges, "socks_port": int(
            q.get("socks_port", 9050))}
        return {"protocol": "tor", "name": p["name"] or "tor", "config": cfg}


class DB:
    def __init__(self, path: Path = DB_FILE):
        self.path = path
        self.encrypted = bool(Settings.get(
            "sqlcipher_key", "")) and _HAS_SQLCIPHER
        self._init()

    def _conn(self):
        if self.encrypted:
            c = sqlcipher3.connect(str(self.path), timeout=10.0)
            c.execute("PRAGMA key = ?", (Settings.get("sqlcipher_key", ""),))
        else:
            c = sqlite3.connect(str(self.path), timeout=10.0)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c

    @contextmanager
    def _txn(self):
        """Connection that commits on success and always closes."""
        c = self._conn()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def _init(self):
        with self._txn() as c:
            try:
                c.execute("PRAGMA journal_mode=WAL")
            except Exception as e:
                logging.warning("DB WAL pragma failed: %s", e)
            c.executescript("""
                CREATE TABLE IF NOT EXISTS groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    name TEXT,
                    url TEXT NOT NULL,
                    last_refresh TIMESTAMP,
                    profile_count INTEGER DEFAULT 0,
                    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER,
                    subscription_id INTEGER,
                    protocol TEXT NOT NULL,
                    name TEXT,
                    raw_link TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    latency_ms INTEGER,
                    real_ping_ms INTEGER,
                    speed_kbps REAL,
                    status TEXT DEFAULT 'unknown',
                    last_tested TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
                    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_profiles_group ON profiles(group_id);
                CREATE INDEX IF NOT EXISTS idx_profiles_status ON profiles(status);
                CREATE INDEX IF NOT EXISTS idx_profiles_latency ON profiles(latency_ms);
            """)
            for col, typ in [("real_ping_ms", "INTEGER"), ("speed_kbps", "REAL")]:
                try:
                    c.execute(f"ALTER TABLE profiles ADD COLUMN {col} {typ}")
                except Exception as e:
                    logging.debug("DB migration %s skipped: %s", col, e)
            try:
                c.execute(
                    "ALTER TABLE subscriptions ADD COLUMN refresh_hours INTEGER DEFAULT 8")
            except Exception as e:
                logging.debug("DB migration refresh_hours skipped: %s", e)
            c.execute("INSERT OR IGNORE INTO groups (name) VALUES ('Default')")

    def add_group(self, name: str) -> Optional[int]:
        try:
            with self._txn() as c:
                cur = c.execute(
                    "INSERT INTO groups (name) VALUES (?)", (name.strip(),))
                audit("group_add", name)
                return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def list_groups(self) -> List[Dict]:
        with self._txn() as c:
            rows = c.execute("""
                SELECT g.*,
                    (SELECT COUNT(*) FROM profiles p WHERE p.group_id = g.id) AS profile_count,
                    (SELECT COUNT(*) FROM profiles p WHERE p.group_id = g.id AND p.status='healthy') AS healthy,
                    (SELECT COUNT(*) FROM profiles p WHERE p.group_id = g.id AND p.status='unhealthy') AS unhealthy,
                    (SELECT COUNT(*) FROM subscriptions s WHERE s.group_id = g.id) AS sub_count
                FROM groups g ORDER BY g.name
            """).fetchall()
            return [dict(r) for r in rows]

    def get_group(self, name_or_id) -> Optional[Dict]:
        with self._txn() as c:
            if isinstance(name_or_id, int) or str(name_or_id).isdigit():
                row = c.execute("SELECT * FROM groups WHERE id = ?",
                                (int(name_or_id),)).fetchone()
            else:
                row = c.execute(
                    "SELECT * FROM groups WHERE name = ?", (name_or_id,)).fetchone()
            return dict(row) if row else None

    def delete_group(self, group_id: int):
        with self._txn() as c:
            c.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        audit("group_delete", str(group_id))

    def rename_group(self, group_id: int, new_name: str) -> bool:
        try:
            with self._txn() as c:
                c.execute("UPDATE groups SET name = ? WHERE id = ?",
                          (new_name, group_id))
            audit("group_rename", f"{group_id} -> {new_name}")
            return True
        except sqlite3.IntegrityError:
            return False

    def add_subscription(self, group_id: int, url: str, name: str = None,
                         refresh_hours: int = 8) -> int:
        with self._txn() as c:
            cur = c.execute(
                "INSERT INTO subscriptions (group_id, name, url, refresh_hours) VALUES (?, ?, ?, ?)",
                (group_id, name or url[:40], url, refresh_hours),
            )
            sid = cur.lastrowid
        audit(
            "sub_add", f"{sid} group={group_id} url={url[:60]} hours={refresh_hours}")
        return sid

    def list_subscriptions(self, group_id: int = None) -> List[Dict]:
        with self._txn() as c:
            if group_id is not None:
                rows = c.execute("SELECT * FROM subscriptions WHERE group_id = ? ORDER BY id",
                                 (group_id,)).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM subscriptions ORDER BY id").fetchall()
            return [dict(r) for r in rows]

    def update_subscription(self, sub_id: int, count: int):
        with self._txn() as c:
            c.execute("UPDATE subscriptions SET last_refresh = ?, profile_count = ? WHERE id = ?",
                      (datetime.now().isoformat(), count, sub_id))

    def delete_subscription(self, sub_id: int):
        with self._txn() as c:
            c.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
        audit("sub_delete", str(sub_id))

    def clear_subscription_profiles(self, sub_id: int) -> int:
        with self._txn() as c:
            cur = c.execute(
                "DELETE FROM profiles WHERE subscription_id = ?", (sub_id,))
            c.execute("UPDATE subscriptions SET profile_count=0, last_refresh=NULL WHERE id = ?",
                      (sub_id,))
        audit("sub_clear_profiles", str(sub_id))
        return cur.rowcount

    def add_profile(self, group_id, subscription_id, protocol, name, raw_link, config) -> Optional[int]:
        try:
            config_json = json.dumps(config)
        except (TypeError, ValueError):
            console.print(f"[warn]Skipping profile with unserializable config: "
                          f"{rich_escape(str(name)[:40])}[/warn]")
            return None
        try:
            with self._txn() as c:
                cur = c.execute("""
                    INSERT INTO profiles (group_id, subscription_id, protocol, name, raw_link, config_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (group_id, subscription_id, protocol, name, raw_link, config_json))
                pid = cur.lastrowid
            audit("profile_add",
                  f"{pid} {protocol} {name[:40] if name else ''}")
            return pid
        except sqlite3.IntegrityError:
            return None

    def upsert_profile(self, group_id, subscription_id, protocol, name, raw_link, config) -> Optional[int]:
        """Insert profile, or update in place (keeping latency history) when an
        identical raw_link already exists for the same subscription."""
        try:
            config_json = json.dumps(config)
        except (TypeError, ValueError):
            return None
        with self._txn() as c:
            row = c.execute(
                "SELECT id FROM profiles WHERE subscription_id = ? AND raw_link = ?",
                (subscription_id, raw_link)).fetchone()
            if row:
                c.execute("""
                    UPDATE profiles SET group_id=?, protocol=?, name=?, config_json=?
                    WHERE id=?
                """, (group_id, protocol, name, config_json, row["id"]))
                return row["id"]
            cur = c.execute("""
                INSERT INTO profiles (group_id, subscription_id, protocol, name, raw_link, config_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (group_id, subscription_id, protocol, name, raw_link, config_json))
            return cur.lastrowid

    def list_profiles(self, group_id: int = None, status: str = None,
                      sub_ids: List[int] = None, group_ids: List[int] = None) -> List[Dict]:
        q = "SELECT * FROM profiles WHERE 1=1"
        args = []
        if group_id is not None:
            q += " AND group_id = ?"
            args.append(group_id)
        if status:
            q += " AND status = ?"
            args.append(status)
        if sub_ids:
            placeholders = ",".join("?" * len(sub_ids))
            q += f" AND subscription_id IN ({placeholders})"
            args.extend(sub_ids)
        if group_ids:
            placeholders = ",".join("?" * len(group_ids))
            q += f" AND group_id IN ({placeholders})"
            args.extend(group_ids)
        q += " ORDER BY latency_ms IS NULL, latency_ms ASC, id"
        last_exc = None
        for attempt in range(3):
            try:
                with self._txn() as c:
                    rows = c.execute(q, args).fetchall()
                out = []
                for r in rows:
                    d = dict(r)
                    d["config"] = json.loads(d["config_json"])
                    out.append(d)
                return out
            except sqlite3.OperationalError as e:
                last_exc = e
                if "locked" in str(e).lower() and attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise
        if last_exc:
            raise last_exc
        return []

    def get_profile(self, profile_id: int) -> Optional[Dict]:
        with self._txn() as c:
            row = c.execute("SELECT * FROM profiles WHERE id = ?",
                            (profile_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["config"] = json.loads(d["config_json"])
            return d

    def update_profile_latency(self, profile_id: int, latency: Optional[int],
                               real_ping: Optional[int] = None,
                               speed_kbps: Optional[float] = None):
        with self._txn() as c:
            status = "healthy" if latency is not None else "unhealthy"
            c.execute("""
                UPDATE profiles
                SET latency_ms = ?, real_ping_ms = COALESCE(?, real_ping_ms),
                    speed_kbps = COALESCE(?, speed_kbps),
                    status = ?, last_tested = ?
                WHERE id = ?
            """, (latency, real_ping, speed_kbps, status,
                  datetime.now().isoformat(), profile_id))

    def move_profile(self, profile_id: int, new_group_id: int) -> bool:
        with self._txn() as c:
            c.execute("UPDATE profiles SET group_id = ? WHERE id = ?",
                      (new_group_id, profile_id))
        audit("profile_move", f"{profile_id} -> group {new_group_id}")
        return True

    def delete_profile(self, profile_id: int):
        with self._txn() as c:
            c.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        audit("profile_delete", str(profile_id))

    def delete_profiles_by_group(self, group_id: int):
        with self._txn() as c:
            c.execute("DELETE FROM profiles WHERE group_id = ?", (group_id,))


def _stream_settings(profile: Dict) -> Dict:
    cfg = profile["config"]
    net = cfg.get("network", "tcp")
    sec = cfg.get("security", "tls")
    if sec == "none" and cfg.get("security_type"):
        sec = cfg["security_type"] or "tls"
    stream: Dict[str, Any] = {"network": net}
    if net == "tcp":
        stream["tcpSettings"] = {"header": {"type": "none"}}
    elif net == "ws":
        path = cfg.get("path", "/")
        if Settings.get("random_subdomain", False):
            path = f"/{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}{path}"
        ws = {"path": path}
        if cfg.get("host_header"):
            ws["headers"] = {"Host": cfg["host_header"]}
        stream["wsSettings"] = ws
    elif net == "grpc":
        stream["grpcSettings"] = {"serviceName": cfg.get(
            "serviceName", ""), "multiMode": False}
    elif net == "h2":
        h2 = {"path": cfg.get("path", "/")}
        if cfg.get("host_header"):
            h2["host"] = [cfg["host_header"]]
        stream["httpSettings"] = h2
    elif net == "httpupgrade":
        stream["httpupgradeSettings"] = {"path": cfg.get(
            "path", "/"), "host": cfg.get("host_header", "")}
    if sec == "tls":
        tls = {"serverName": cfg.get("sni", cfg["address"]),
               "fingerprint": cfg.get("fp", "chrome"),
               "allowInsecure": cfg.get("allowInsecure", False)}
        if cfg.get("alpn"):
            tls["alpn"] = cfg["alpn"]
        stream["security"] = "tls"
        stream["tlsSettings"] = tls
    elif sec == "reality":
        stream["security"] = "reality"
        stream["realitySettings"] = {
            "serverName": cfg.get("sni", cfg["address"]),
            "fingerprint": cfg.get("fp", "chrome"),
            "publicKey": cfg.get("pbk", ""), "shortId": cfg.get("sid", ""),
            "spiderX": cfg.get("spx", "/"),
        }
    else:
        stream["security"] = "none"
    return stream


def _build_outbound(profile: Dict, tag: str = "proxy") -> Dict:
    proto = profile["protocol"]
    cfg = profile["config"]
    out: Dict[str, Any] = {"tag": tag,
                           "streamSettings": _stream_settings(profile)}
    if proto == "vmess":
        u = {"id": cfg["id"], "alterId": cfg.get(
            "alterId", 0), "security": cfg.get("security", "auto")}
        out["protocol"] = "vmess"
        out["settings"] = {
            "vnext": [{"address": cfg["address"], "port": cfg["port"], "users": [u]}]}
    elif proto == "vless":
        u = {"id": cfg["id"], "encryption": cfg.get("encryption", "none")}
        if cfg.get("flow"):
            u["flow"] = cfg["flow"]
        out["protocol"] = "vless"
        out["settings"] = {
            "vnext": [{"address": cfg["address"], "port": cfg["port"], "users": [u]}]}
    elif proto == "trojan":
        out["protocol"] = "trojan"
        out["settings"] = {"servers": [
            {"address": cfg["address"], "port": cfg["port"], "password": cfg["password"]}]}
    elif proto == "ss":
        out["protocol"] = "shadowsocks"
        out["settings"] = {"servers": [{"address": cfg["address"], "port": cfg["port"],
                                       "method": cfg["method"], "password": cfg["password"]}]}
    elif proto == "socks":
        out["protocol"] = "socks"
        user = {}
        if cfg.get("username"):
            user = {"user": cfg["username"], "pass": cfg["password"]}
        out["settings"] = {"servers": [
            {"address": cfg["address"], "port": cfg["port"], **user}]}
    else:
        raise ValueError(f"Protocol '{proto}' requires a different core")
    if Settings.get("mux", True) and proto in ("vmess", "vless", "trojan"):
        out["mux"] = {"enabled": True, "concurrency": int(
            Settings.get("mux_concurrency", 8))}
    return out


def build_xray_config(profile: Dict, extra_proxies: List[Dict] = None,
                      ports_override: Tuple[int, int] = None) -> Dict:
    socks_port = int(ports_override[0]) if ports_override else int(
        Settings.get("socks_port", 10808))
    http_port = int(ports_override[1]) if ports_override else int(
        Settings.get("http_port", 10810))
    dns = Settings.get("dns", "1.1.1.1")
    inbounds = [
        {"tag": "socks-in", "port": socks_port, "listen": "127.0.0.1", "protocol": "socks",
         "settings": {"auth": "noauth", "udp": True}},
        {"tag": "http-in", "port": http_port, "listen": "127.0.0.1",
            "protocol": "http", "settings": {}},
    ]

    def _routing_rules():
        rules = []
        if Settings.get("routing", "bypass_iran") == "bypass_iran":
            rules.append(
                {"type": "field", "domain": IRAN_DOMAINS, "outboundTag": "direct"})
            if Settings.get("iran_ip_bypass", True):
                rules.append({"type": "field", "ip": [
                             "geoip:ir"], "outboundTag": "direct"})
                rules.append(
                    {"type": "field", "ip": IRAN_IP_RANGES, "outboundTag": "direct"})
        if Settings.get("china_bypass", False):
            rules.append({"type": "field", "domain": [
                         "geosite:cn"], "outboundTag": "direct"})
            rules.append({"type": "field", "ip": [
                         "geoip:cn"], "outboundTag": "direct"})
        if Settings.get("russia_bypass", False):
            rules.append({"type": "field", "domain": [
                         "geosite:category-ru"], "outboundTag": "direct"})
            rules.append({"type": "field", "ip": [
                         "geoip:ru"], "outboundTag": "direct"})
        rules.append({"type": "field", "ip": LAN_IPS, "outboundTag": "direct"})
        rules.append({"type": "field", "ip": [
                     "geoip:private"], "outboundTag": "direct"})
        if Settings.get("geosite_ads_block", False):
            rules.append({"type": "field", "domain": [
                         "geosite:category-ads-all"], "outboundTag": "blocked"})
        for r in Settings.get("custom_routing_rules", []):
            rules.append(r)
        return rules

    if Settings.get("load_balancing", False) and extra_proxies:
        all_profiles = [profile] + list(extra_proxies)
        outbounds, proxy_tags = [], []
        for i, p in enumerate(all_profiles):
            tag = f"proxy-{i}"
            try:
                outbounds.append(_build_outbound(p, tag=tag))
                proxy_tags.append(tag)
            except ValueError:
                continue
        if not proxy_tags:
            outbounds = [_build_outbound(profile)]
            proxy_tags = ["proxy"]
        outbounds += [
            {"tag": "direct", "protocol": "freedom", "settings": {}},
            {"tag": "blocked", "protocol": "blackhole", "settings": {}},
        ]
        if Settings.get("fragment", True):
            outbounds.append({
                "tag": "fragment", "protocol": "freedom",
                "settings": {"fragment": {"packets": "tlshello",
                                          "length": str(Settings.get("fragment_length", "100-200")),
                                          "interval": str(Settings.get("fragment_interval", "10-20"))}},
                "streamSettings": {"sockopt": {"tcpNoDelay": True}},
            })
            for ob in outbounds:
                if ob.get("tag", "").startswith("proxy-") or ob.get("tag") == "proxy":
                    ob["streamSettings"].setdefault("sockopt", {})[
                        "dialerProxy"] = "fragment"
        routing = {"domainStrategy": "IPIfNonMatch", "rules": _routing_rules()}
        strategy = Settings.get("lb_strategy", "leastPing")
        routing["balancers"] = [{"tag": "balancer-1", "selector": proxy_tags,
                                 "strategy": {"type": strategy}}]
        routing["rules"].append(
            {"type": "field", "network": "tcp,udp", "balancerTag": "balancer-1"})
        cfg = {
            "log": {"loglevel": "warning"},
            "dns": {"servers": [dns]},
            "inbounds": inbounds, "outbounds": outbounds, "routing": routing,
        }
        if strategy == "leastPing":
            cfg["observatory"] = {
                "subjectSelector": proxy_tags,
                "probeURL": "https://www.google.com/generate_204",
                "probeInterval": Settings.get("lb_observatory_interval", "30s"),
                "enableConcurrency": True,
            }
        else:
            cfg["burstObservatory"] = {
                "subjectSelector": proxy_tags,
                "pingConfig": {
                    "destination": "http://www.google.com/generate_204",
                    "connectivity": "http://www.google.com/generate_204",
                    "interval": Settings.get("lb_observatory_interval", "30s"),
                    "sampling": 2, "timeout": "5s",
                }
            }
        return cfg

    outbounds = [
        _build_outbound(profile),
        {"tag": "direct", "protocol": "freedom", "settings": {}},
        {"tag": "blocked", "protocol": "blackhole", "settings": {}},
    ]
    if Settings.get("fragment", True):
        outbounds.append({
            "tag": "fragment", "protocol": "freedom",
            "settings": {"fragment": {"packets": "tlshello",
                                      "length": str(Settings.get("fragment_length", "100-200")),
                                      "interval": str(Settings.get("fragment_interval", "10-20"))}},
            "streamSettings": {"sockopt": {"tcpNoDelay": True}},
        })
        outbounds[0]["streamSettings"].setdefault(
            "sockopt", {})["dialerProxy"] = "fragment"
    routing = {"domainStrategy": "IPIfNonMatch", "rules": _routing_rules()}
    routing["rules"].append(
        {"type": "field", "network": "tcp,udp", "outboundTag": "proxy"})
    return {
        "log": {"loglevel": "warning"},
        "dns": {"servers": [dns]},
        "inbounds": inbounds, "outbounds": outbounds, "routing": routing,
    }


def build_hysteria_config_text(profile: Dict) -> str:
    cfg = profile["config"]
    socks_port = int(Settings.get("socks_port", 10808))
    http_port = int(Settings.get("http_port", 10810))
    lines = [f"server: {cfg['address']}:{cfg['port']}"]
    if cfg.get("password"):
        lines.append(f"auth: {cfg['password']}")
    lines += ["tls:", f"  sni: {cfg.get('sni', cfg['address'])}",
              f"  insecure: {'true' if cfg.get('insecure') else 'false'}"]
    if cfg.get("obfs"):
        lines += ["obfs:", f"  type: {cfg['obfs']}", f"  {cfg['obfs']}:",
                  f"    password: {cfg.get('obfs_password', '')}"]
    lines += ["socks5:", f"  listen: 127.0.0.1:{socks_port}",
              "http:", f"  listen: 127.0.0.1:{http_port}"]
    lines += ["bandwidth:", f"  up: {int(cfg.get('up_mbps', 50))} mbps",
              f"  down: {int(cfg.get('down_mbps', 50))} mbps"]
    return "\n".join(lines) + "\n"


def build_wireguard_config_text(profile: Dict) -> str:
    cfg = profile["config"]
    lines = ["[Interface]", f"PrivateKey = {cfg.get('private_key', '')}"]
    if cfg.get("local_address"):
        lines.append(f"Address = {cfg['local_address']}")
    if cfg.get("dns"):
        lines.append(f"DNS = {cfg['dns']}")
    if cfg.get("mtu"):
        lines.append(f"MTU = {cfg['mtu']}")
    lines += ["", "[Peer]", f"PublicKey = {cfg.get('public_key', '')}"]
    if cfg.get("preshared_key"):
        lines.append(f"PresharedKey = {cfg['preshared_key']}")
    host = cfg.get("peer_endpoint_host") or cfg.get("address")
    port = cfg.get("peer_endpoint_port") or cfg.get("port")
    lines.append(f"Endpoint = {host}:{port}")
    lines.append(f"AllowedIPs = {cfg.get('allowed_ips', '0.0.0.0/0')}")
    if cfg.get("keepalive"):
        lines.append(f"PersistentKeepalive = {cfg['keepalive']}")
    return "\n".join(lines) + "\n"


def parse_wireguard_conf_file(path: Path) -> Optional[Dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    section = None
    cfg: Dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            section = line.strip("[]").lower()
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip().lower()
            v = v.strip()
            if section == "interface":
                if k == "privatekey":
                    cfg["private_key"] = v
                elif k == "address":
                    cfg["local_address"] = v
                elif k == "dns":
                    cfg["dns"] = v
                elif k == "mtu":
                    cfg["mtu"] = int(v) if v.isdigit() else 1420
            elif section == "peer":
                if k == "publickey":
                    cfg["public_key"] = v
                elif k == "presharedkey":
                    cfg["preshared_key"] = v
                elif k == "endpoint" and ":" in v:
                    h, p = v.rsplit(":", 1)
                    cfg["peer_endpoint_host"] = h.strip("[]")
                    try:
                        cfg["peer_endpoint_port"] = int(p)
                    except ValueError:
                        pass
                elif k == "allowedips":
                    cfg["allowed_ips"] = v
                elif k == "persistentkeepalive":
                    try:
                        cfg["keepalive"] = int(v)
                    except ValueError:
                        pass
    if not cfg.get("private_key") or not cfg.get("public_key"):
        return None
    cfg.setdefault("peer_endpoint_port", 51820)
    cfg.setdefault("peer_endpoint_host", "")
    # Keep endpoint in address/port for generic display, but never overwrite
    # the interface's own local_address with the peer endpoint.
    cfg["address"] = cfg.get("peer_endpoint_host", "")
    cfg["port"] = cfg.get("peer_endpoint_port", 51820)
    return {"protocol": "wireguard", "name": f"wg-{path.stem}", "config": cfg}


async def tcp_ping(host: str, port: int, timeout: float = 3.0) -> Optional[int]:
    writer = None
    try:
        start = time.perf_counter()
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        ms = int((time.perf_counter()-start)*1000)
        return ms
    except Exception:
        return None
    finally:
        if writer:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


async def real_ping_via_proxy(host: str, port: int, socks_port: int, timeout: float = 5.0) -> Optional[int]:
    try:
        start = time.perf_counter()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", socks_port), timeout=timeout)
        writer.write(b"\x05\x01\x00")
        await writer.drain()
        if await asyncio.wait_for(reader.read(2), timeout=timeout) != b"\x05\x00":
            writer.close()
            return None
        hb = host.encode()
        writer.write(b"\x05\x01\x00\x03" +
                     bytes([len(hb)]) + hb + struct.pack(">H", port))
        await writer.drain()
        head = await asyncio.wait_for(reader.readexactly(4), timeout=timeout)
        if head[1] != 0:
            writer.close()
            return None
        atyp = head[3]
        if atyp == 1:
            await reader.readexactly(4)
        elif atyp == 3:
            n = (await reader.readexactly(1))[0]
            await reader.readexactly(n)
        elif atyp == 4:
            await reader.readexactly(16)
        await reader.readexactly(2)
        ms = int((time.perf_counter()-start)*1000)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return ms
    except Exception:
        return None


async def _ping_profile(profile: Dict) -> Tuple[int, Optional[int]]:
    cfg = profile.get("config", {})
    host = cfg.get("address", "")
    port = int(cfg.get("port", 0) or 0)
    if not host or not port:
        return profile["id"], None
    return profile["id"], await tcp_ping(host, port, timeout=float(Settings.get("timeout", 3.0)))


async def test_profiles_async(profiles: List[Dict], on_progress=None) -> List[Dict]:
    concurrency = max(1, int(Settings.get("concurrency", 20)))
    if screen_off_mode():
        concurrency = max(1, concurrency // 3)
    if not battery_ok():
        concurrency = max(1, concurrency // 2)
    sem = asyncio.Semaphore(concurrency)
    results = {}

    async def bound(p):
        async with sem:
            pid, ms = await _ping_profile(p)
            results[pid] = ms
            if on_progress:
                on_progress()
    await asyncio.gather(*(bound(p) for p in profiles))
    for p in profiles:
        ms = results.get(p["id"])
        p["latency_ms"] = ms
        db.update_profile_latency(p["id"], ms)
    return profiles


def _ssl_ctx():
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def speed_test_via_proxy(socks_port: int, test_url: str = None,
                               timeout: float = 20.0) -> Optional[float]:
    if test_url is None:
        test_url = "http://speed.cloudflare.com/__down?bytes=5000000"
    parsed = urllib.parse.urlparse(test_url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not host:
        return None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", socks_port), timeout=10)
        writer.write(b"\x05\x01\x00")
        await writer.drain()
        if await asyncio.wait_for(reader.read(2), timeout=10) != b"\x05\x00":
            writer.close()
            return None
        hb = host.encode()
        writer.write(b"\x05\x01\x00\x03" +
                     bytes([len(hb)]) + hb + struct.pack(">H", port))
        await writer.drain()
        # SOCKS5 reply: VER REP RSV ATYP BND.ADDR BND.PORT — variable length.
        head = await asyncio.wait_for(reader.readexactly(4), timeout=10)
        if head[1] != 0:
            writer.close()
            return None
        atyp = head[3]
        if atyp == 1:
            await reader.readexactly(4)       # IPv4
        elif atyp == 3:                                  # domain
            n = (await reader.readexactly(1))[0]
            await reader.readexactly(n)
        elif atyp == 4:
            await reader.readexactly(16)     # IPv6
        await reader.readexactly(2)                      # BND.PORT
        if parsed.scheme == "https":
            try:
                writer = await asyncio.wait_for(
                    writer.start_tls(_ssl_ctx(), server_hostname=host), timeout=10)
            except Exception:
                writer.close()
                return None
        req = f"GET {parsed.path or '/'} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"
        writer.write(req.encode())
        await writer.drain()
        start = time.perf_counter()
        total = 0
        while True:
            chunk = await asyncio.wait_for(reader.read(8192), timeout=timeout)
            if not chunk:
                break
            total += len(chunk)
            if time.perf_counter() - start > 15:
                break
        elapsed = max(0.01, time.perf_counter() - start)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return (total / 1024.0) / elapsed
    except Exception:
        return None


def fetch_subscription(url: str, timeout: int = 20,
                       quiet: bool = False) -> List[str]:
    try:
        ctx = None
        if url.lower().startswith("https"):
            if Settings.get("subscription_skip_tls_verify"):
                ctx = ssl._create_unverified_context()
            else:
                ctx = ssl.create_default_context()
        req = urllib.request.Request(
            url, headers={"User-Agent": f"MultiProxySuite/{VERSION}"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read(10 * 1024 * 1024)
    except Exception as e:
        if quiet:
            logging.warning("Subscription fetch failed (%s): %s", url, e)
        else:
            logging.error("Subscription fetch failed (%s): %s\n%s",
                          url, e, traceback.format_exc())
            console.print(f"[fail]Fetch error: {rich_escape(str(e))}[/fail]")
        return []
    text = raw.decode("utf-8", errors="ignore")
    if "://" not in text:
        try:
            s = text.strip().replace("-", "+").replace("_", "/")
            pad = "=" * (-len(s) % 4)
            decoded = base64.b64decode(
                s+pad, validate=True).decode("utf-8", errors="ignore")
            if "://" in decoded:
                text = decoded
        except Exception as e:
            logging.debug("subscription b64 fallback failed: %s", e)
    links = []
    for line in text.splitlines():
        line = line.strip()
        if line and "://" in line and not line.startswith("#"):
            scheme = line.split("://", 1)[0].lower()
            if scheme in SUPPORTED_PROTOCOLS:
                links.append(line)
    return links


class XrayRunner:
    def __init__(self): self.proc: Optional[subprocess.Popen] = None

    def _env(self) -> Dict[str, str]:
        env = os.environ.copy()
        env["XRAY_LOCATION_ASSET"] = str(GEO_DIR.resolve())
        return env

    def launch(self, profile: Dict, extra_proxies: List[Dict] = None,
               ports_override: Tuple[int, int] = None) -> bool:
        if self.proc and self.proc.poll() is None:
            self.stop()
        xray = find_xray()
        if not xray:
            console.print(
                "[fail]Xray binary not found. Run dependency check.[/fail]")
            return False

        try:
            st = os.stat(xray)
            if not (st.st_mode & 0o111):
                os.chmod(xray, 0o755)
        except OSError:
            pass

        if not DependencyManager.ensure_geo_files():
            console.print("[warn]Continuing with limited geo support.[/warn]")

        try:
            config = build_xray_config(profile, extra_proxies=extra_proxies,
                                       ports_override=ports_override)
        except ValueError as e:
            console.print(
                f"[fail]Cannot build config: {rich_escape(str(e))}[/fail]")
            return False

        def clean_text(t: str) -> str:
            if not t:
                return ""
            t = re.sub(r'\x1b\[[0-9;]*m', '', t)
            t = t.replace('\x00', '')
            return t.strip()

        ACTIVE_CONFIG.write_text(json.dumps(config, indent=2))

        if Settings.get("xray_test_before_launch", False):
            console.print(
                "[dim]Verifying config with xray run -test ...[/dim]")
            try:
                t = subprocess.run(
                    [xray, "run", "-test", "-c", str(ACTIVE_CONFIG)],
                    capture_output=True, timeout=20, env=self._env(),
                )
                out = clean_text((t.stdout or b"").decode(
                    "utf-8", errors="replace"))
                err = clean_text((t.stderr or b"").decode(
                    "utf-8", errors="replace"))
                combined = (out + "\n" + err).strip()
                if t.returncode != 0:
                    if combined:
                        console.print(
                            "[warn]xray -test reported errors (will try real launch):[/warn]")
                        console.print(
                            f"[dim]{rich_escape(combined[:1500])}[/dim]")
                    else:
                        console.print("[warn]xray -test returned no output "
                                      "(Android quirk); will verify via real launch...[/warn]")
            except subprocess.TimeoutExpired:
                console.print(
                    "[warn]Config test timed out; continuing.[/warn]")
            except Exception as e:
                console.print(
                    f"[warn]Config test error: {rich_escape(str(e))}[/warn]")

        max_attempts = int(Settings.get("safe_launch_retries", 3))
        profiles_to_try = [profile]
        try:
            all_profiles = db.list_profiles()
            healthy = [p for p in all_profiles if p.get("latency_ms") is not None
                       and p.get("protocol") in ("vmess", "vless", "trojan", "ss", "socks", "hysteria2")]
            healthy.sort(key=lambda p: p["latency_ms"])
            for p in healthy:
                if p["id"] != profile.get("id") and p not in profiles_to_try:
                    profiles_to_try.append(p)
                    if len(profiles_to_try) >= max_attempts:
                        break
        except Exception as e:
            logging.warning(f"Safe-launch candidate fetch failed: {e}")

        for attempt, try_profile in enumerate(profiles_to_try, 1):
            if attempt > 1:
                console.print(f"[info]Safe-launch attempt {attempt}/{len(profiles_to_try)}: "
                              f"{rich_escape(try_profile['name'])}...[/info]")
                try:
                    config = build_xray_config(try_profile, extra_proxies=extra_proxies,
                                               ports_override=ports_override)
                except ValueError:
                    continue
                ACTIVE_CONFIG.write_text(json.dumps(config, indent=2))

            console.print(f"[info]Launching Xray: {xray}[/info]")
            try:
                self.proc = subprocess.Popen(
                    [xray, "run", "-c", str(ACTIVE_CONFIG)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL, env=self._env(),
                )
            except OSError as e:
                console.print(
                    f"[fail]Launch failed: {rich_escape(str(e))}[/fail]")
                return False

            time.sleep(3.0)
            if self.proc.poll() is not None:
                # stdout is DEVNULL now; diagnose via a one-shot foreground run
                try:
                    t = subprocess.run(
                        [xray, "run", "-test", "-c", str(ACTIVE_CONFIG)],
                        capture_output=True, timeout=15, env=self._env())
                    text = clean_text(((t.stdout or b"") + (t.stderr or b"")).decode(
                        "utf-8", errors="replace"))
                except Exception:
                    text = ""
                console.print(
                    f"[fail]Xray exited (code {self.proc.returncode}):[/fail]")
                if text:
                    console.print(f"[dim]{rich_escape(text[:1500])}[/dim]")
                else:
                    console.print("[dim]No output captured.[/dim]")
                if attempt < len(profiles_to_try):
                    continue
                return False
            return True
        return False

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def is_running(
        self): return self.proc is not None and self.proc.poll() is None


class PsiphonRunner:
    def __init__(self):
        self.proc: Optional[subprocess.Popen] = None
        self.config_path: Optional[Path] = None
        self.upstream_runner: Optional["ProxyRunner"] = None

    def _build_config(self, profile: Dict, mode: str = "direct",
                      upstream_port: int = None) -> Dict:
        cfg = profile.get("config", {})
        socks_port = int(Settings.get("socks_port", 10808))
        http_port = int(Settings.get("http_port", 10810))
        psiphon_cfg = {
            "PropagationChannelId": "FFFFFFFFFFFFFFFF",
            "SponsorId": "FFFFFFFFFFFFFFFF",
            "RemoteServerListUrl": "",
            "RemoteServerListSignaturePublicKey": "",
            "DataStoreDirectory": str(OUTPUT_DIR / "psiphon_datastore"),
            "DataStoreTempDirectory": str(OUTPUT_DIR / "psiphon_temp"),
            "LogFilename": str(OUTPUT_DIR / "psiphon.log"),
            "LocalHttpProxyPort": http_port,
            "LocalSocksProxyPort": socks_port,
            "EgressRegion": cfg.get("region") or Settings.get("psiphon_region", ""),
            "TunnelProtocol": "",
            "ConnectionWorkerPoolSize": 10,
            "TunnelPoolSize": 2,
            "PortForwardFailureThreshold": 10,
            "UpstreamHttpProxyAddress": "",
            "UpstreamProxyUrl": "",
        }
        if mode == "chain" and upstream_port:
            psiphon_cfg["UpstreamProxyUrl"] = f"socks5://127.0.0.1:{upstream_port}"
            console.print(
                f"[info]Psiphon upstream proxy: socks5://127.0.0.1:{upstream_port}[/info]")

        if mode == "dns":
            psiphon_cfg["MeekFrontingDomain"] = cfg.get(
                "meek_fronting_domain", "")
            psiphon_cfg["MeekFrontingAddresses"] = cfg.get(
                "meek_fronting_addresses", [])
            if cfg.get("config_url"):
                psiphon_cfg["RemoteServerListUrl"] = cfg["config_url"]

        if Settings.get("psiphon_config_url"):
            try:
                req = urllib.request.Request(Settings.get("psiphon_config_url"),
                                             headers={"User-Agent": f"MPS/{VERSION}"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    remote_cfg = json.loads(r.read().decode())
                psiphon_cfg.update(remote_cfg)
                console.print(
                    "[success]Psiphon config loaded from URL.[/success]")
            except Exception as e:
                console.print(
                    f"[warn]Failed to load Psiphon config URL: {rich_escape(str(e))}[/warn]")

        if Settings.get("psiphon_use_dns") or Settings.get("psiphon_dns_source"):
            dns_source = Settings.get("psiphon_dns_source", "")
            dns_list = []
            if dns_source.startswith("http"):
                try:
                    req = urllib.request.Request(
                        dns_source, headers={"User-Agent": f"MPS/{VERSION}"})
                    with urllib.request.urlopen(req, timeout=15) as r:
                        dns_list = [ln.strip() for ln in r.read().decode().splitlines()
                                    if ln.strip() and not ln.startswith("#")]
                except Exception as e:
                    console.print(
                        f"[warn]DNS URL load failed: {rich_escape(str(e))}[/warn]")
            elif Path(dns_source).exists():
                try:
                    dns_list = [ln.strip() for ln in Path(dns_source).read_text().splitlines()
                                if ln.strip() and not ln.startswith("#")]
                except Exception as e:
                    console.print(
                        f"[warn]DNS file load failed: {rich_escape(str(e))}[/warn]")
            if dns_list:
                psiphon_cfg["DnsServerList"] = dns_list
                console.print(
                    f"[success]Loaded {len(dns_list)} DNS servers.[/success]")

        return psiphon_cfg

    def launch(self, profile: Dict) -> bool:
        if self.proc and self.proc.poll() is None:
            self.stop()
        psiphon_bin = find_psiphon()
        if not psiphon_bin:
            console.print(
                "[fail]Psiphon binary not found. Run dependency check.[/fail]")
            return False
        try:
            st = os.stat(psiphon_bin)
            if not (st.st_mode & 0o111):
                os.chmod(psiphon_bin, 0o755)
                console.print(f"[info]Fixed permissions: {psiphon_bin}[/info]")
        except OSError as e:
            console.print(
                f"[fail]Cannot chmod psiphon: {rich_escape(str(e))}[/fail]")
            return False

        mode = Settings.get("psiphon_mode", "direct")
        upstream_port = None
        if mode == "chain":
            up_id = Settings.get("psiphon_upstream_profile_id")
            if up_id:
                up_profile = db.get_profile(up_id)
                if up_profile:
                    console.print(
                        f"[info]Starting upstream Xray: {rich_escape(up_profile['name'])}[/info]")
                    self.upstream_runner = XrayRunner()
                    # Upstream Xray must NOT bind the main socks_port — psiphon
                    # itself listens there. Bind it to socks_port_2 instead.
                    upstream_port = int(Settings.get("socks_port_2", 10809))
                    ok = self.upstream_runner.launch(
                        up_profile, ports_override=(upstream_port, upstream_port + 1))
                    if not ok:
                        console.print(
                            "[fail]Upstream Xray failed. Falling back to direct.[/fail]")
                        mode = "direct"
                        upstream_port = None
                    else:
                        time.sleep(2)

        psiphon_cfg = self._build_config(
            profile, mode=mode, upstream_port=upstream_port)
        OUTPUT_DIR.joinpath("psiphon_datastore").mkdir(exist_ok=True)
        OUTPUT_DIR.joinpath("psiphon_temp").mkdir(exist_ok=True)
        self.config_path = OUTPUT_DIR / "active_psiphon.json"
        self.config_path.write_text(json.dumps(psiphon_cfg, indent=2))

        console.print(
            f"[info]Launching Psiphon ({mode} mode): {psiphon_bin}[/info]")
        try:
            self.proc = subprocess.Popen(
                [psiphon_bin, "--config", str(self.config_path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except OSError as e:
            console.print(
                f"[fail]Psiphon launch failed: {rich_escape(str(e))}[/fail]")
            if self.upstream_runner:
                self.upstream_runner.stop()
            return False

        console.print("[dim]Waiting for Psiphon tunnel...[/dim]")
        for i in range(20):
            time.sleep(1)
            if self.proc.poll() is not None:
                break
        if self.proc.poll() is not None:
            console.print(f"[fail]Psiphon exited (code {self.proc.returncode}) "
                          f"within 20s. Check psiphon datastore/logs.[/fail]")
            if self.upstream_runner:
                self.upstream_runner.stop()
            return False

        console.print("[success]Psiphon tunnel established.[/success]")
        return True

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        if self.upstream_runner:
            self.upstream_runner.stop()
            self.upstream_runner = None

    def is_running(
        self): return self.proc is not None and self.proc.poll() is None


class Hysteria2Runner:
    def __init__(self): self.proc = None; self.config_path = None

    def launch(self, profile: Dict) -> bool:
        if self.proc and self.proc.poll() is None:
            self.stop()
        h = find_hysteria()
        if not h:
            console.print("[fail]Hysteria binary not found.[/fail]")
            return False
        self.config_path = ACTIVE_HY2
        self.config_path.write_text(build_hysteria_config_text(profile))
        console.print(f"[info]Launching Hysteria2: {h}[/info]")
        try:
            self.proc = subprocess.Popen([h, "client", "-c", str(self.config_path)],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            console.print(f"[fail]Launch failed: {rich_escape(str(e))}[/fail]")
            return False
        time.sleep(1.5)
        if self.proc.poll() is not None:
            console.print(
                "[fail]Hysteria exited immediately (see mps.log).[/fail]")
            return False
        return True

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def is_running(
        self): return self.proc is not None and self.proc.poll() is None


class WireGuardRunner:
    IFACE = "mps-wg0"
    def __init__(self): self.iface_up = False; self.conf_path = None

    def launch(self, profile: Dict) -> bool:
        self.conf_path = OUTPUT_DIR / f"{self.IFACE}.conf"
        self.conf_path.write_text(build_wireguard_config_text(profile))
        console.print(f"[info]WireGuard config: {self.conf_path}[/info]")
        wg = find_wg_quick()
        if not wg:
            console.print("[warn]wg-quick not found. Config exported.[/warn]")
            Sys.notify("WireGuard config ready", str(self.conf_path))
            return False
        cmd = [wg, "up", str(self.conf_path)]
        if _is_unix() and not is_admin():
            if shutil.which("sudo"):
                cmd = ["sudo", "-n"] + cmd
            else:
                console.print(
                    f"[warn]Root required. Run: sudo wg-quick up {self.conf_path}[/warn]")
                return False
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                self.iface_up = True
                console.print("[success]WireGuard up.[/success]")
                return True
            err = (r.stderr or r.stdout or "")[:300]
            console.print(f"[fail]wg-quick: {rich_escape(err)}[/fail]")
            return False
        except Exception as e:
            console.print(f"[fail]{rich_escape(str(e))}[/fail]")
            return False

    def stop(self):
        if not self.iface_up or not self.conf_path:
            return
        wg = find_wg_quick()
        if not wg:
            return
        cmd = [wg, "down", str(self.conf_path)]
        if _is_unix() and not is_admin() and shutil.which("sudo"):
            cmd = ["sudo", "-n"] + cmd
        try:
            subprocess.run(cmd, capture_output=True, timeout=15)
        except Exception as e:
            logging.warning("wg-quick down failed: %s", e)
        self.iface_up = False

    def is_running(self): return self.iface_up


class ExternalRunner:
    def __init__(self, binary_finder, args_builder):
        self.binary_finder = binary_finder
        self.args_builder = args_builder
        self.proc = None
        self.config_path = None

    def launch(self, profile: Dict) -> bool:
        bin_path = self.binary_finder()
        if not bin_path:
            console.print(
                f"[fail]Binary for {profile['protocol']} not found.[/fail]")
            return False
        try:
            args, self.config_path = self.args_builder(profile, bin_path)
        except Exception as e:
            console.print(
                f"[fail]Config build failed: {rich_escape(str(e))}[/fail]")
            return False
        if self.config_path:
            console.print(f"[info]Config saved: {self.config_path}[/info]")
        console.print(
            f"[info]Launching: {Path(bin_path).name} (args hidden)[/info]")
        try:
            self.proc = subprocess.Popen(
                [bin_path]+args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            console.print(f"[fail]Launch failed: {rich_escape(str(e))}[/fail]")
            return False
        time.sleep(1.5)
        if self.proc.poll() is not None:
            console.print("[fail]Exited immediately (see mps.log).[/fail]")
            return False
        return True

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    def is_running(
        self): return self.proc is not None and self.proc.poll() is None


def _build_singbox_args(profile: Dict, bin_path: str) -> Tuple[List[str], Path]:
    proto = profile["protocol"]
    cfg = profile["config"]
    socks = int(Settings.get("socks_port", 10808))
    http = int(Settings.get("http_port", 10810))
    inbound = [{"type": "socks", "listen": "127.0.0.1", "listen_port": socks},
               {"type": "http", "listen": "127.0.0.1", "listen_port": http}]
    if proto == "tuic":
        outbound = {"type": "tuic", "server": cfg["address"], "server_port": cfg["port"],
                    "uuid": cfg["uuid"], "password": cfg["password"],
                    "tls": {"enabled": True, "server_name": cfg.get("sni", cfg["address"]),
                            "insecure": cfg.get("allow_insecure", False),
                            "alpn": cfg.get("alpn", ["h3"])},
                    "congestion_control": cfg.get("congestion_control", "bbr"),
                    "udp_relay_mode": cfg.get("udp_relay_mode", "native")}
    elif proto == "shadowtls":
        outbound = {"type": "shadowtls", "server": cfg["address"], "server_port": cfg["port"],
                    "version": cfg.get("version", 3), "password": cfg["password"],
                    "tls": {"enabled": True, "server_name": cfg.get("sni", cfg["address"]), "insecure": False}}
    elif proto == "naive":
        outbound = {"type": "naive", "server": cfg["address"], "server_port": cfg["port"],
                    "username": cfg.get("username", ""), "password": cfg.get("password", ""),
                    "tls": {"enabled": True, "server_name": cfg.get("sni", cfg["address"]),
                            "insecure": cfg.get("insecure", False)}}
    else:
        raise ValueError("Unsupported sing-box protocol")
    config = {"log": {"level": "warn"}, "inbounds": inbound,
              "outbounds": [outbound, {"type": "direct", "tag": "direct"}]}
    ACTIVE_SINGBOX.write_text(json.dumps(config, indent=2))
    return (["run", "-c", str(ACTIVE_SINGBOX)], ACTIVE_SINGBOX)


def _build_dnstt_args(profile: Dict, bin_path: str) -> Tuple[List[str], Path]:
    cfg = profile["config"]
    socks = int(Settings.get("socks_port", 10808))
    args = ["-doh", cfg.get("resolver", ""),
            cfg.get("domain", ""), f"127.0.0.1:{socks}"]
    if cfg.get("pubkey"):
        args = ["-pubkey", cfg["pubkey"]] + args
    return (args, None)


def _build_ssh_args(profile: Dict, bin_path: str) -> Tuple[List[str], Path]:
    cfg = profile["config"]
    socks = int(Settings.get("socks_port", 10808))
    args = ["-N", "-D", f"127.0.0.1:{socks}", "-p", str(cfg.get("port", 22))]
    if cfg.get("private_key_path"):
        args += ["-i", cfg["private_key_path"]]
    args.append(f"{cfg.get('username', '')}@{cfg.get('address', '')}")
    return (args, None)


def _build_tor_args(profile: Dict, bin_path: str) -> Tuple[List[str], Path]:
    cfg = profile["config"]
    socks = int(Settings.get("socks_port", 10808))
    lines = [f"SocksPort {socks}",
             "ControlPort 9051", "CookieAuthentication 1"]
    for b in cfg.get("bridges", []):
        lines.append(f"Bridge {b}")
    path = OUTPUT_DIR / "active_torrc"
    path.write_text("\n".join(lines))
    return (["-f", str(path)], path)


class RateTracker:
    """Tracks network throughput via psutil (optional) or /proc fallback."""

    def __init__(self):
        self._psutil = None
        try:
            import psutil
            self._psutil = psutil
        except ImportError:
            pass
        self._last = None
        self._last_t = 0.0
        self.rate_up = 0.0
        self.rate_down = 0.0
        self.session_up = 0
        self.session_down = 0
        self._session_base = None

    def _snapshot(self):
        if self._psutil:
            io = self._psutil.net_io_counters()
            return (io.bytes_sent, io.bytes_recv)
        try:
            with open("/proc/net/dev") as f:
                sent = recv = 0
                for line in f.readlines()[2:]:
                    parts = line.split(":")
                    if len(parts) != 2 or parts[0].strip() == "lo":
                        continue
                    vals = parts[1].split()
                    if len(vals) >= 9:
                        recv += int(vals[0])
                        sent += int(vals[8])
                return (sent, recv)
        except Exception as e:
            logging.debug("rate _snapshot failed: %s", e)
            return None

    def update(self):
        """Sample counters; returns (up_bps, down_bps) or (0, 0)."""
        snap = self._snapshot()
        if snap is None:
            return (0.0, 0.0)
        now = time.time()
        if self._last is not None:
            dt = now - self._last_t
            if dt > 0.2:
                d_up = snap[0] - self._last[0]
                d_down = snap[1] - self._last[1]
                if d_up >= 0 and d_down >= 0:
                    self.rate_up = d_up / dt
                    self.rate_down = d_down / dt
                    if self._session_base is not None:
                        self.session_up = max(0, snap[0] - self._session_base[0])
                        self.session_down = max(0, snap[1] - self._session_base[1])
        self._last = snap
        self._last_t = now
        return (self.rate_up, self.rate_down)

    def reset_session(self):
        """Mark current counters as the session baseline."""
        snap = self._snapshot()
        self._session_base = snap
        self._last = snap
        self._last_t = time.time()
        self.session_up = 0
        self.session_down = 0
        self.rate_up = 0.0
        self.rate_down = 0.0

    def clear(self):
        self.rate_up = 0.0
        self.rate_down = 0.0
        self.session_up = 0
        self.session_down = 0
        self._session_base = None


RATE = RateTracker()


def _fmt_rate(bps: float) -> str:
    if bps >= 1024 * 1024:
        return f"{bps / 1024 / 1024:.1f} MB/s"
    if bps >= 1024:
        return f"{bps / 1024:.0f} KB/s"
    return f"{bps:.0f} B/s"


def _fmt_bytes(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


class ProxyRunner:
    def __init__(self):
        self.xray = XrayRunner()
        self.hysteria = Hysteria2Runner()
        self.wireguard = WireGuardRunner()
        self.psiphon = PsiphonRunner()
        self.external: Optional[ExternalRunner] = None
        self.active_kind = None
        self.active_profile = None
        self.start_time = None

    def launch(self, profile: Dict, extra_proxies: List[Dict] = None) -> bool:
        proto = profile.get("protocol", "")
        self.stop()
        if proto == "psiphon":
            ok = self.psiphon.launch(profile)
            self.active_kind = "psiphon" if ok else None
        elif proto == "hysteria2":
            ok = self.hysteria.launch(profile)
            self.active_kind = "hysteria" if ok else None
        elif proto == "wireguard":
            ok = self.wireguard.launch(profile)
            self.active_kind = "wireguard" if ok else None
        elif proto in ("vmess", "vless", "trojan", "ss", "socks"):
            ok = self.xray.launch(profile, extra_proxies=extra_proxies)
            self.active_kind = "xray" if ok else None
        elif proto == "tuic":
            self.external = ExternalRunner(find_singbox, _build_singbox_args)
            ok = self.external.launch(profile)
            self.active_kind = "sing-box" if ok else None
        elif proto == "shadowtls":
            self.external = ExternalRunner(find_singbox, _build_singbox_args)
            ok = self.external.launch(profile)
            self.active_kind = "sing-box" if ok else None
        elif proto == "naive":
            self.external = ExternalRunner(find_singbox, _build_singbox_args)
            ok = self.external.launch(profile)
            self.active_kind = "sing-box" if ok else None
        elif proto == "dnstt":
            self.external = ExternalRunner(find_dnstt, _build_dnstt_args)
            ok = self.external.launch(profile)
            self.active_kind = "dnstt" if ok else None
        elif proto == "ssh":
            self.external = ExternalRunner(
                lambda: shutil.which("ssh"), _build_ssh_args)
            ok = self.external.launch(profile)
            self.active_kind = "ssh" if ok else None
        elif proto == "tor":
            self.external = ExternalRunner(find_tor, _build_tor_args)
            ok = self.external.launch(profile)
            self.active_kind = "tor" if ok else None
        else:
            console.print(f"[fail]Unsupported protocol: {proto}[/fail]")
            return False
        if ok:
            self.active_profile = profile
            self.start_time = time.time()
            RATE.reset_session()
            logging.info(
                f"Connected to {profile.get('name')} via {self.active_kind}")
        return ok

    def stop(self):
        self.xray.stop()
        self.hysteria.stop()
        self.wireguard.stop()
        self.psiphon.stop()
        if self.external:
            self.external.stop()
        self.active_kind = None
        self.active_profile = None
        self.start_time = None
        RATE.clear()

    def is_running(self):
        if self.active_kind == "xray":
            return self.xray.is_running()
        if self.active_kind == "hysteria":
            return self.hysteria.is_running()
        if self.active_kind == "wireguard":
            return self.wireguard.is_running()
        if self.active_kind == "psiphon":
            return self.psiphon.is_running()
        if self.external:
            return self.external.is_running()
        return False


class Watchdog:
    def __init__(self, runner: ProxyRunner, profiles_provider):
        self.runner = runner
        self.profiles_provider = profiles_provider
        self.thread = None
        self._stop = threading.Event()
        self.last_ping_ms = None

    def start(self):
        if not Settings.get("failover", False):
            return
        if self.thread and self.thread.is_alive():
            return
        self._stop.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        try:
            asyncio.run(self._async_loop())
        except Exception as e:
            logging.error(f"Watchdog: {e}")

    async def _async_loop(self):
        interval = int(Settings.get("failover_interval_sec", 30))
        max_fails = int(Settings.get("failover_max_fails", 3))
        socks = int(Settings.get("socks_port", 10808))
        fails = 0
        while not self._stop.is_set():
            for _ in range(interval):
                if self._stop.is_set():
                    return
                await asyncio.sleep(1.0)
            if not self.runner.is_running():
                fails += 1
            else:
                ms = await real_ping_via_proxy("www.google.com", 443, socks, timeout=6.0)
                self.last_ping_ms = ms
                fails = 0 if ms else fails+1
            if fails >= max_fails:
                cur = self.runner.active_profile or {}
                cands = [p for p in self.profiles_provider()
                         if p.get("latency_ms") is not None and p.get("id") != cur.get("id")
                         and p.get("protocol") in ("vmess", "vless", "trojan", "ss", "socks", "hysteria2", "tuic", "psiphon")]
                if cands:
                    cands.sort(key=lambda p: p["latency_ms"])
                    new = cands[0]
                    console.print(
                        f"[warn]Failover → {rich_escape(new['name'])}[/warn]")
                    Sys.tts("Failover")
                    Sys.notify("Auto-Failover", new["name"])
                    self.runner.launch(new)
                fails = 0

    def stop(self):
        self._stop.set()
        if self.thread:
            self.thread.join(timeout=3)


class AutoRotator:
    def __init__(self, runner: ProxyRunner, profiles_provider):
        self.runner = runner
        self.profiles_provider = profiles_provider
        self.thread = None
        self._stop = threading.Event()

    def start(self):
        minutes = float(Settings.get("auto_rotate_minutes", 0) or 0)
        if minutes <= 0:
            return
        if self.thread and self.thread.is_alive():
            return
        self._stop.clear()
        self.thread = threading.Thread(
            target=self._loop, args=(minutes,), daemon=True)
        self.thread.start()
        console.print(f"[info]Auto-Rotate: every {minutes} min[/info]")

    def _loop(self, minutes: float):
        sec = minutes * 60
        while not self._stop.wait(sec):
            healthy = [p for p in self.profiles_provider() if p.get(
                "latency_ms") is not None]
            if not healthy:
                continue
            cur_id = (self.runner.active_profile or {}).get("id")
            cands = [p for p in healthy if p["id"] != cur_id]
            if not cands:
                continue
            new = random.choice(cands)
            console.print(
                f"[info]Auto-Rotate → {rich_escape(new['name'])}[/info]")
            Sys.notify("Auto-Rotate", new["name"])
            self.runner.launch(new)

    def stop(self):
        self._stop.set()
        if self.thread:
            self.thread.join(timeout=2)


class SubscriptionRefresher:
    def __init__(self): self.thread = None; self._stop = threading.Event()

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self._stop.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        if self._stop.wait(60):
            return
        while not self._stop.is_set():
            try:
                self._refresh_due()
            except Exception as e:
                logging.error(f"Auto-refresh: {e}")
            if self._stop.wait(300):
                return

    def _refresh_due(self):
        subs = db.list_subscriptions()
        if not subs:
            return
        now = time.time()
        total_added = 0
        for s in subs:
            hours = s.get("refresh_hours") or Settings.get(
                "refresh_interval_hours", 8)
            if hours <= 0:
                continue
            last = s.get("last_refresh")
            if last:
                try:
                    last_ts = datetime.fromisoformat(last).timestamp()
                except Exception:
                    last_ts = 0
                if now - last_ts < hours * 3600:
                    continue
            links = fetch_subscription(s["url"], quiet=True)
            if not links:
                continue
            added = 0
            for link in links:
                parsed = URLParser.parse(link)
                if not parsed:
                    continue
                db.upsert_profile(s["group_id"], s["id"], parsed["protocol"],
                                  parsed["name"], link, parsed["config"])
                added += 1
            # Drop profiles that vanished from the subscription, keeping
            # latency history for the ones that remain.
            with db._txn() as c:
                c.execute("""
                    DELETE FROM profiles
                    WHERE subscription_id = ?
                      AND raw_link NOT IN (SELECT value FROM json_each(?))
                """, (s["id"], json.dumps(links)))
            db.update_subscription(s["id"], added)
            total_added += added
            logging.info(
                f"Subscription refreshed: {s.get('name', '?')} → {added} profiles")
        if total_added:
            Sys.notify("Subscriptions refreshed", f"{total_added} profiles")
            Sys.tts("Subscriptions refreshed")

    def stop(self):
        self._stop.set()
        if self.thread:
            self.thread.join(timeout=2)


class ProfileAutoRefresher:
    def __init__(self, menu):
        self.menu = menu
        self.thread = None
        self._stop = threading.Event()
        self.last_refresh = 0.0
        self.next_refresh = 0.0

    def start(self):
        minutes = float(Settings.get("auto_refresh_profiles_minutes", 10))
        if minutes <= 0:
            return
        if self.thread and self.thread.is_alive():
            return
        self._stop.clear()
        self.last_refresh = time.time()
        self.next_refresh = self.last_refresh + minutes * 60
        self.thread = threading.Thread(
            target=self._loop, args=(minutes,), daemon=True)
        self.thread.start()
        console.print(
            f"[info]Profile auto-refresh: every {minutes:.0f} min[/info]")

    def _loop(self, minutes):
        interval = minutes * 60
        while not self._stop.wait(interval):
            try:
                self._do_refresh()
            except Exception as e:
                logging.error(f"Profile auto-refresh: {e}")

    def _do_refresh(self):
        self.last_refresh = time.time()
        self.next_refresh = self.last_refresh + \
            float(Settings.get("auto_refresh_profiles_minutes", 10)) * 60
        profiles = db.list_profiles(
            sub_ids=Settings.get("active_subscription_ids") or None,
            group_ids=Settings.get("active_group_ids") or None)
        if not profiles:
            return
        try:
            asyncio.run(test_profiles_async(profiles))
        except Exception as e:
            logging.error(f"Auto-refresh ping: {e}")
            return
        if not Settings.get("auto_switch_enabled", True):
            return
        profiles = db.list_profiles()
        healthy = [p for p in profiles if p.get("latency_ms") is not None]
        if not healthy:
            return
        healthy.sort(key=lambda p: p["latency_ms"])
        best = healthy[0]
        current = self.menu.runner.active_profile
        cur_id = current.get("id") if current else None
        if cur_id != best.get("id"):
            self.menu.runner.launch(best)
            logging.info(
                f"Auto-switched to {best.get('name')} ({best.get('latency_ms')}ms)")

    def stop(self):
        self._stop.set()
        if self.thread:
            self.thread.join(timeout=2)

    def seconds_to_next(self) -> int:
        if self.next_refresh <= 0:
            return -1
        return max(0, int(self.next_refresh - time.time()))


def create_backup() -> Optional[Path]:
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = BACKUP_DIR / f"mps_backup_{ts}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if DB_FILE.exists() and not db.encrypted:
                zf.write(DB_FILE, "profiles.db")
            if SETTINGS_FILE.exists():
                zf.write(SETTINGS_FILE, "settings.json")
            if AUDIT_FILE.exists():
                zf.write(AUDIT_FILE, "audit.log")
        console.print(f"[success]Backup: {zip_path}[/success]")
        Sys.notify("Backup created", str(zip_path.name))
        audit("backup", str(zip_path))
        return zip_path
    except Exception as e:
        console.print(f"[fail]Backup failed: {rich_escape(str(e))}[/fail]")
        return None


def restore_backup(zip_path: Path) -> bool:
    if not zip_path.exists():
        console.print("[fail]File not found.[/fail]")
        return False
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            if "profiles.db" in names:
                if db.encrypted:
                    console.print(
                        "[warn]Encrypted DB — cannot restore plain db.[/warn]")
                else:
                    if DB_FILE.exists():
                        shutil.copy2(DB_FILE, DB_FILE.with_suffix(".bak"))
                    zf.extract("profiles.db", OUTPUT_DIR)
            if "settings.json" in names:
                zf.extract("settings.json", OUTPUT_DIR)
                Settings.load()
            if "audit.log" in names:
                zf.extract("audit.log", OUTPUT_DIR)
        console.print("[success]Restored. Restart for full effect.[/success]")
        audit("restore", str(zip_path))
        return True
    except Exception as e:
        console.print(f"[fail]Restore failed: {rich_escape(str(e))}[/fail]")
        return False


def qr_export(profile: Dict):
    if not _HAS_QR:
        console.print("[warn]Install `qrcode[pil]` to use QR export.[/warn]")
        console.print(
            f"[dim]Link: {rich_escape(profile.get('raw_link', ''))}[/dim]")
        return
    link = profile.get("raw_link", "")
    if not link:
        console.print("[fail]No raw link.[/fail]")
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(link)
    qr.make(fit=True)
    try:
        qr.print_ascii(invert=True)
    except Exception as e:
        logging.warning("qr print_ascii failed: %s", e)
    out_png = OUTPUT_DIR / f"qr_{profile['id']}.png"
    try:
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(str(out_png))
        console.print(f"[success]PNG: {out_png}[/success]")
    except Exception as e:
        console.print(f"[warn]PNG save failed: {rich_escape(str(e))}[/warn]")
    Sys.clipboard_set(link)


def qr_import():
    txt = Sys.clipboard_get().strip()
    if not txt:
        txt = Prompt.ask("Paste QR content (share-link)").strip()
    if not txt:
        console.print("[fail]Empty.[/fail]")
        return
    parsed = URLParser.parse(txt)
    if not parsed:
        console.print("[fail]Unrecognized link.[/fail]")
        return
    gid_row = db.get_group("Default")
    if not gid_row:
        groups = db.list_groups()
        gid_row = groups[0] if groups else None
    if not gid_row:
        db.add_group("Default")
        gid_row = db.get_group("Default")
    if not gid_row:
        console.print("[fail]No group available for import.[/fail]")
        return
    gid = gid_row["id"]
    pid = db.add_profile(
        gid, None, parsed["protocol"], parsed["name"], txt, parsed["config"])
    if pid:
        console.print(
            f"[success]Imported '{rich_escape(parsed['name'])}'.[/success]")
    else:
        console.print("[fail]Add failed.[/fail]")


class DashboardKeyListener:
    def __init__(self):
        self.queue = queue.Queue()
        self._stop = threading.Event()
        self.thread = None
        self._old_term = None
        self._saved = False

    def start(self):
        if os.name != 'nt':
            try:
                import termios
                import tty
                self._old_term = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
                self._saved = True
            except Exception as e:
                logging.debug("key listener termios setup failed: %s", e)
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        if os.name == 'nt':
            import msvcrt
            while not self._stop.is_set():
                # Per-iteration guard: one bad call must never kill the
                # listener thread (that would silently disable ALL hotkeys).
                try:
                    if msvcrt.kbhit():
                        ch = msvcrt.getwch()
                        # Windows sends arrow/function keys as two chars:
                        # a 0xE0/0x00 prefix followed by a scan code. The
                        # scan code always follows, so read it blocking —
                        # otherwise scan codes like 'Q' (PgDn) leak in as
                        # phantom regular keys.
                        if ch in ("\x00", "\xe0"):
                            try:
                                scan = msvcrt.getwch()
                            except Exception:
                                scan = ""
                            arrow = {"H": "\x1b[A", "P": "\x1b[B",
                                     "M": "\x1b[C", "K": "\x1b[D"}.get(scan)
                            if arrow:
                                self.queue.put(arrow)
                        elif ch:
                            self.queue.put(ch)
                    else:
                        time.sleep(0.05)
                except Exception:
                    time.sleep(0.05)
        else:
            import select
            while not self._stop.is_set():
                try:
                    r, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if r:
                        ch = sys.stdin.read(1)
                        if ch:
                            self.queue.put(ch)
                except (OSError, ValueError):
                    time.sleep(0.1)
                except Exception:
                    time.sleep(0.05)

    def stop(self):
        self._stop.set()
        if self.thread:
            self.thread.join(timeout=1.0)
        if self._saved and self._old_term is not None:
            try:
                import termios
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_term)
            except Exception as e:
                logging.debug("key listener termios restore failed: %s", e)

    def get(self, timeout=0.1):
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None


_PUBLIC_IP_CACHE = {"ip": None, "ts": 0.0}


def _fetch_public_ip(socks_port: int, timeout: float = 5.0) -> Optional[str]:
    """Fetch exit/public IP through the local SOCKS5 proxy (raw SOCKS5 + HTTP GET)."""
    now = time.time()
    if _PUBLIC_IP_CACHE["ip"] and now - _PUBLIC_IP_CACHE["ts"] < 120:
        return _PUBLIC_IP_CACHE["ip"]
    try:
        import socket as _socket
        s = _socket.create_connection(
            ("127.0.0.1", socks_port), timeout=timeout)
        s.settimeout(timeout)
        s.sendall(b"\x05\x01\x00")
        if s.recv(2) != b"\x05\x00":
            s.close()
            return None
        host = b"api.ipify.org"
        s.sendall(b"\x05\x01\x00\x03" +
                  bytes([len(host)]) + host + struct.pack(">H", 80))
        resp = s.recv(4)
        if len(resp) < 4 or resp[1] != 0:
            s.close()
            return None
        atyp = resp[3]
        if atyp == 1:
            s.recv(4)
        elif atyp == 3:
            n = s.recv(1)[0]
            s.recv(n)
        elif atyp == 4:
            s.recv(16)
        s.recv(2)
        s.sendall(b"GET /?format=text HTTP/1.1\r\nHost: api.ipify.org\r\n"
                  b"User-Agent: MPS\r\nConnection: close\r\n\r\n")
        data = b""
        while len(data) < 4096:
            chunk = s.recv(1024)
            if not chunk:
                break
            data += chunk
        s.close()
        body = data.split(b"\r\n\r\n", 1)
        if len(body) < 2:
            return None
        ip = body[1].decode("ascii", "ignore").strip()
        if ip and 7 <= len(ip) <= 45 and all(c in "0123456789.abcdefABCDEF:" for c in ip):
            _PUBLIC_IP_CACHE["ip"] = ip
            _PUBLIC_IP_CACHE["ts"] = now
            return ip
    except Exception as e:
        logging.debug("public IP fetch failed: %s", e)
    return None


def render_dashboard(runner: ProxyRunner, ping_ms=None, watchdog=None, menu=None) -> Panel:
    socks = int(Settings.get("socks_port", 10808))
    running = runner.is_running()
    # --- status line ---
    if running:
        p = runner.active_profile or {}
        cfg = p.get("config", {}) or {}
        host = cfg.get("address") or cfg.get("peer_endpoint_host") or "?"
        port = cfg.get("port") or cfg.get("peer_endpoint_port") or "?"
        status = Text.assemble(("● ", "bold green"),
                               ("CONNECTED", "bold green"))
        conn_rows = [
            ("Profile", str(p.get("name", "?"))[:34]),
            ("Protocol", str(p.get("protocol", "?")).upper()),
            ("Endpoint", f"{host}:{port}"),
            ("Core", str(runner.active_kind or "?")),
        ]
    else:
        status = Text.assemble(
            ("○ ", "bold red"), ("DISCONNECTED", "bold red"))
        conn_rows = []
    # --- latency + uptime ---
    if ping_ms is not None:
        color = "green" if ping_ms < 200 else (
            "yellow" if ping_ms < 800 else "red")
        latency = f"[{color}]{ping_ms} ms[/]"
    else:
        latency = "—"
    uptime = "—"
    if running and runner.start_time:
        up = int(time.time() - runner.start_time)
        h, r = divmod(up, 3600)
        m, s = divmod(r, 60)
        uptime = f"{h:02d}:{m:02d}:{s:02d}"
    # --- public IP (cached, fetched via proxy) ---
    pub_ip = _fetch_public_ip(socks) if running else None
    ip_disp = pub_ip if pub_ip else ("…" if running else "—")
    # --- left column: connection ---
    left = Table.grid(padding=(0, 1))
    left.add_column(style="cyan", min_width=10, no_wrap=True)
    left.add_column(style="green", overflow="fold")
    left.add_row("Status", status)
    for k, v in conn_rows:
        left.add_row(k, rich_escape(str(v)))
    left.add_row("SOCKS5", f"127.0.0.1:{socks}")
    left.add_row("HTTP", f"127.0.0.1:{Settings.get('http_port')}")
    left.add_row("Latency", latency)
    left.add_row("Uptime", uptime)
    if running:
        RATE.update()
        rate = f"[cyan]↑[/cyan] {_fmt_rate(RATE.rate_up)}  [cyan]↓[/cyan] {_fmt_rate(RATE.rate_down)}"
        left.add_row("Rate", rate)
        left.add_row("Session", f"↑ {_fmt_bytes(RATE.session_up)}  ↓ {_fmt_bytes(RATE.session_down)}")
    else:
        left.add_row("Rate", "—")
        left.add_row("Session", "—")
    # --- right column: automation ---
    right = Table.grid(padding=(0, 1))
    right.add_column(style="cyan", min_width=10, no_wrap=True)
    right.add_column(style="green", overflow="fold")
    auto = Settings.get("auto_switch_enabled", True)
    right.add_row("Auto-Sw", "ON" if auto else "[warn]OFF[/]")
    right.add_row("Failover", "ON" if Settings.get("failover") else "OFF")
    right.add_row("Load Bal.", "ON" if Settings.get(
        "load_balancing") else "OFF")
    ar_min = float(Settings.get("auto_refresh_profiles_minutes", 10) or 0)
    nxt = "—"
    if ar_min > 0 and menu is not None:
        ref = getattr(menu, "auto_refresher", None)
        if ref:
            secs = ref.seconds_to_next()
            if secs >= 0:
                m, s = divmod(int(secs), 60)
                nxt = f"{m}m {s:02d}s"
            else:
                nxt = f"every {ar_min:.0f}m"
    right.add_row("Re-ping", nxt)
    right.add_row("Public IP", ip_disp)
    active_subs = Settings.get("active_subscription_ids") or []
    active_groups = Settings.get("active_group_ids") or []
    if active_subs or active_groups:
        right.add_row("Filter", f"{len(active_subs)}s/{len(active_groups)}g")
    # --- two-row hotkey bar ---
    hk1 = Table.grid(padding=(0, 1))
    hk1.add_column(justify="center", ratio=1)
    hk1.add_row("[bold]Enter[/] best  [bold]p[/] pick  [bold]r[/] re-ping")
    hk2 = Table.grid(padding=(0, 1))
    hk2.add_column(justify="center", ratio=1)
    hk2.add_row("[bold]d[/] disconnect  [bold]q[/] exit")
    body = Columns([left, right], padding=(0, 2), expand=False, equal=False)
    inner = Table.grid()
    inner.add_column()
    inner.add_row(body)
    inner.add_row(Rule(style="dim"))
    inner.add_row(hk1)
    inner.add_row(hk2)
    return Panel(inner, title="[bold magenta]📊 MultiProxy[/bold magenta]",
                 border_style="magenta", expand=False)


class Menu:
    def __init__(self):
        self.runner = ProxyRunner()
        self.watchdog = Watchdog(self.runner, profiles_provider=lambda: db.list_profiles(
            sub_ids=Settings.get("active_subscription_ids") or None,
            group_ids=Settings.get("active_group_ids") or None))
        self.rotator = AutoRotator(self.runner, profiles_provider=lambda: db.list_profiles(
            sub_ids=Settings.get("active_subscription_ids") or None,
            group_ids=Settings.get("active_group_ids") or None))
        self.refresher = SubscriptionRefresher()
        self.auto_refresher = ProfileAutoRefresher(self)

    def _pick_group(self, allow_create=True) -> Optional[int]:
        groups = db.list_groups()
        if not groups:
            if allow_create and Confirm.ask("[yellow]No groups. Create one?[/yellow]", default=True):
                return self._create_group()
            return None
        table = Table(title="Groups")
        table.add_column("#", width=3)
        table.add_column("Name")
        table.add_column("Profiles", justify="right")
        table.add_column("Healthy", justify="right")
        table.add_column("Unhealthy", justify="right")
        table.add_column("Subs", justify="right")
        for i, g in enumerate(groups, 1):
            table.add_row(str(i), g["name"], str(g["profile_count"]),
                          str(g["healthy"]), str(g["unhealthy"]), str(g["sub_count"]))
        console.print(table)
        if allow_create:
            console.print("  [cyan]0[/cyan]. + Create new group")
        choices = [str(i) for i in range(1, len(groups)+1)] + \
            (["0"] if allow_create else [])
        c = Prompt.ask("Select group", choices=choices)
        if c == "0":
            return self._create_group()
        return groups[int(c)-1]["id"]

    def _create_group(self) -> Optional[int]:
        name = Prompt.ask("New group name").strip()
        if not name:
            return None
        gid = db.add_group(name)
        if gid:
            console.print(
                f"[success]Group '{rich_escape(name)}' created (id={gid}).[/success]")
            return gid
        console.print("[fail]Group already exists.[/fail]")
        e = db.get_group(name)
        return e["id"] if e else None

    def _import_links(self, links, group_id, subscription_id=None):
        added = 0
        with db._txn() as c:
            rows = c.execute(
                "SELECT raw_link FROM profiles WHERE group_id=?", (group_id,)).fetchall()
            seen = {r["raw_link"] for r in rows}
        for link in links:
            if link in seen:
                continue
            parsed = URLParser.parse(link)
            if not parsed:
                continue
            db.add_profile(group_id, subscription_id, parsed["protocol"],
                           parsed["name"], link, parsed["config"])
            seen.add(link)
            added += 1
        return added

    def _get_active_profiles(self):
        return db.list_profiles(
            sub_ids=Settings.get("active_subscription_ids") or None,
            group_ids=Settings.get("active_group_ids") or None)

    # ---- Dependencies menu (Stage 2) ------------------------------------
    _DEPS = [
        # (key, label, finder, installer, required)
        ("xray",     "Xray-core",      find_xray,
         lambda f: DependencyManager.ensure_xray(force=f), True),
        ("psiphon",  "Psiphon",        find_psiphon,
         lambda f: DependencyManager.ensure_psiphon(force=f), True),
        ("geo",      "Geo files",      None,
         lambda f: DependencyManager.ensure_geo_files(force=True), True),
        ("hysteria", "Hysteria2",      find_hysteria,
         lambda f: DependencyManager.ensure_hysteria(force=f), False),
        ("singbox",  "sing-box",       find_singbox,
         lambda f: DependencyManager.ensure_singbox(force=f), False),
        ("tor",      "Tor",            find_tor,
         lambda f: DependencyManager.ensure_tor(force=f), False),
        ("wg",       "WireGuard",      find_wg_quick,
         lambda f: DependencyManager.ensure_wg(force=f), False),
        ("dnstt",    "dnstt-client",   find_dnstt,
         lambda f: DependencyManager.ensure_dnstt(force=f), False),
        ("pypkg",    "Python packages", None,
         lambda f: DependencyManager.ensure_python_packages(), False),
        ("syspkg",   "System packages", None,
         lambda f: DependencyManager.ensure_system_packages(), False),
    ]

    def dependencies_menu(self):
        while True:
            console.clear()
            console.print(Rule("[title]🔧 Dependencies[/title]"))
            table = Table(box=box.ROUNDED, expand=False)
            table.add_column("#", style="cyan", width=3, justify="right")
            table.add_column("Component", style="bold", min_width=16)
            table.add_column("Status", min_width=30, overflow="fold")
            table.add_column("Kind", min_width=9)
            for i, (key, label, finder, installer, required) in enumerate(self._DEPS, 1):
                if finder is None:
                    status = "[green]✓ managed[/green]"
                else:
                    p = finder()
                    status = f"[green]✓ {rich_escape(str(p))}[/green]" if p else "[red]✗ missing[/red]"
                kind = "[yellow]required[/yellow]" if required else "optional"
                table.add_row(str(i), label, status, kind)
            console.print(table)
            console.print(
                "  [cyan]a[/cyan]. Install all missing   "
                "[cyan]r[/cyan]. Reinstall all   [cyan]0[/cyan]. Back")
            c = Prompt.ask("Action", default="0")
            if c == "0":
                break
            elif c == "a":
                for key, label, finder, installer, required in self._DEPS:
                    if finder is None:
                        continue
                    if not finder():
                        console.print(
                            Rule(f"[title]Installing {label}[/title]"))
                        try:
                            installer(False)
                        except Exception as e:
                            console.print(
                                f"[fail]{label}: {rich_escape(str(e))}[/fail]")
                console.print("[success]Install-all pass complete.[/success]")
            elif c == "r":
                if not Confirm.ask("Force reinstall ALL components?", default=False):
                    continue
                for key, label, finder, installer, required in self._DEPS:
                    console.print(Rule(f"[title]Reinstalling {label}[/title]"))
                    try:
                        installer(True)
                    except Exception as e:
                        console.print(
                            f"[fail]{label}: {rich_escape(str(e))}[/fail]")
                console.print("[success]Reinstall pass complete.[/success]")
            elif c.isdigit() and 1 <= int(c) <= len(self._DEPS):
                key, label, finder, installer, required = self._DEPS[int(c)-1]
                console.print(Rule(f"[title]{label}[/title]"))
                try:
                    p = installer(True)
                    if p:
                        console.print(f"[success]{label}: {p}[/success]")
                    else:
                        console.print(
                            f"[warn]{label}: not available on this platform.[/warn]")
                except Exception as e:
                    console.print(
                        f"[fail]{label}: {type(e).__name__}: {rich_escape(str(e))}[/fail]")
            else:
                console.print("[fail]Invalid choice.[/fail]")
            _pause_for_output()

    # ---- Setup wizard (Stage 3) -----------------------------------------
    def setup_wizard(self) -> bool:
        """Guided first-run setup: deps → group → sources → ports → routing
        → connect options. Returns True if at least one profile exists."""
        console.print(Rule("[title]🧙 Setup Wizard[/title]"))
        console.print("[info]This wizard configures everything needed to get "
                      "you connected. Press Ctrl+C to abort at any time.[/info]")

        # 1) Dependencies
        console.print(Rule("[title]Step 1/6 — Dependencies[/title]"))
        missing = []
        for key, label, finder, installer, required in self._DEPS:
            if finder is None:
                continue
            if required and not finder():
                missing.append(label)
        if missing:
            console.print(
                f"[warn]Missing required: {', '.join(missing)}[/warn]")
            if Confirm.ask("Install them now?", default=True):
                for key, label, finder, installer, required in self._DEPS:
                    if finder is None or not required:
                        continue
                    if not finder():
                        try:
                            installer(False)
                        except Exception as e:
                            console.print(
                                f"[fail]{label}: {rich_escape(str(e))}[/fail]")
        else:
            console.print(
                "[success]All required dependencies present.[/success]")

        # 2) Group
        console.print(Rule("[title]Step 2/6 — Group[/title]"))
        gid = self._pick_group(allow_create=True)
        if not gid:
            console.print("[fail]A group is required. Wizard aborted.[/fail]")
            return False

        # 3) Sources
        console.print(Rule("[title]Step 3/6 — Profile sources[/title]"))
        console.print("  [cyan]1[/cyan]. Subscription URL")
        console.print("  [cyan]2[/cyan]. Paste links manually")
        console.print("  [cyan]3[/cyan]. WireGuard .conf file")
        console.print("  [cyan]4[/cyan]. Psiphon (auto, no source needed)")
        console.print("  [cyan]0[/cyan]. Skip")
        src = Prompt.ask("Source type", default="1",
                         choices=["0", "1", "2", "3", "4"])
        added = 0
        if src == "1":
            url = Prompt.ask("Subscription URL").strip()
            if url:
                name = Prompt.ask("Label (optional)",
                                  default="").strip() or None
                hours_str = Prompt.ask("Refresh every N hours (0=off)",
                                       default=str(Settings.get("refresh_interval_hours", 8)))
                try:
                    hours = int(float(hours_str))
                except ValueError:
                    hours = 8
                sub_id = db.add_subscription(
                    gid, url, name, refresh_hours=hours)
                console.print("[info]Fetching...[/info]")
                links = fetch_subscription(url)
                if links:
                    added = self._import_links(links, gid, sub_id)
                    db.update_subscription(sub_id, added)
                    console.print(
                        f"[success]Imported {added} profiles.[/success]")
                else:
                    console.print("[fail]Fetch returned no links (URL kept; "
                                  "refresh later from Subscriptions menu).[/fail]")
        elif src == "2":
            console.print(
                "[info]Paste links, one per line. Empty line to finish.[/info]")
            lines = []
            while True:
                try:
                    ln = input()
                except EOFError:
                    break
                if not ln.strip():
                    break
                lines.append(ln.strip())
            if lines:
                added = self._import_links(lines, gid)
            console.print(
                f"[success]Imported {added}/{len(lines) if lines else 0}.[/success]")
        elif src == "3":
            path = Path(Prompt.ask("Path to .conf").strip()).expanduser()
            if path.exists():
                parsed = parse_wireguard_conf_file(path)
                if parsed:
                    raw = f"wireguard://file://{path.resolve()}"
                    if db.add_profile(gid, None, "wireguard", parsed["name"], raw, parsed["config"]):
                        added = 1
                        console.print(
                            f"[success]Imported '{rich_escape(parsed['name'])}'[/success]")
                else:
                    console.print("[fail]Invalid WG config.[/fail]")
            else:
                console.print("[fail]File not found.[/fail]")
        elif src == "4":
            region = Prompt.ask("Psiphon region (empty=auto)",
                                default=Settings.get("psiphon_region", ""))
            Settings.set("psiphon_region", region)
            port = int(Settings.get("socks_port", 10808))
            raw = f"psiphon://?region={region}&socks_port={port}"
            cfg = {"region": region, "config_url": "",
                   "local_socks_port": port, "extra_args": ""}
            if db.add_profile(gid, None, "psiphon", f"Psiphon ({region or 'auto'})", raw, cfg):
                added = 1
                console.print("[success]Psiphon profile added.[/success]")

        # 4) Ports
        console.print(Rule("[title]Step 4/6 — Local ports[/title]"))
        socks = IntPrompt.ask(
            "SOCKS5 port", default=Settings.get("socks_port", 10808))
        http = IntPrompt.ask(
            "HTTP port", default=Settings.get("http_port", 10810))
        Settings.set("socks_port", socks)
        Settings.set("http_port", http)
        console.print(f"[success]Ports: SOCKS5={socks}, HTTP={http}[/success]")

        # 5) Routing
        console.print(Rule("[title]Step 5/6 — Routing[/title]"))
        Settings.set("routing", Prompt.ask(
            "Routing mode", choices=["bypass_iran", "global", "custom"],
            default=Settings.get("routing", "bypass_iran")))
        if Confirm.ask("Bypass Iran IPs (GeoIP + ranges)?", default=Settings.get("iran_ip_bypass", True)):
            Settings.set("iran_ip_bypass", True)
        else:
            Settings.set("iran_ip_bypass", False)
        if Confirm.ask("Bypass China IPs?", default=Settings.get("china_bypass", False)):
            Settings.set("china_bypass", True)
        if Confirm.ask("Bypass Russia IPs?", default=Settings.get("russia_bypass", False)):
            Settings.set("russia_bypass", False)

        # 6) Connect options
        console.print(Rule("[title]Step 6/6 — Connect options[/title]"))
        Settings.set("auto_switch_enabled", Confirm.ask(
            "Auto-switch to best profile on failure?",
            default=Settings.get("auto_switch_enabled", True)))
        Settings.set("failover", Confirm.ask(
            "Enable watchdog failover?", default=Settings.get("failover", False)))
        Settings.set("auto_rotate_minutes", 0 if not Confirm.ask(
            "Auto-rotate periodically?", default=bool(Settings.get("auto_rotate_minutes", 0)))
            else IntPrompt.ask("Rotate every N minutes",
                               default=Settings.get("auto_rotate_minutes", 30) or 30))
        console.print("[success]Wizard configuration saved.[/success]")

        # Finish: test + connect
        if added > 0 and Confirm.ask("Test profiles and connect now?", default=True):
            self._test_all()
            best = self._find_best_profile()
            if best:
                self._do_connect(best, quiet=True)
                console.print(
                    f"[success]Connected: {rich_escape(best['name'])}[/success]")
                Sys.tts("Setup complete. Connected.")
            else:
                console.print(
                    "[warn]No usable profile found; try Auto-Pilot later.[/warn]")
        elif added == 0:
            console.print("[warn]No profiles imported yet — add sources from the "
                          "Subscriptions or Profiles menu, then run Auto-Pilot.[/warn]")
        return db.list_profiles() and True or False

    def main_menu(self):
        while True:
            console.clear()
            status = ("[success]● Connected[/success]" if self.runner.is_running()
                      else "[muted]○ Disconnected[/muted]")
            if self.runner.is_running():
                p = self.runner.active_profile or {}
                status += f" [dim]{rich_escape(p.get('name', '?')[:24])}[/dim]"
            hdr = Table.grid(padding=(0, 2))
            hdr.add_column(justify="left")
            hdr.add_column(justify="right")
            hdr.add_row(f"[title]🌐 MultiProxy v{VERSION}[/title]", status)
            console.print(Panel(hdr, box=box.SIMPLE, padding=(0, 0)))

            menu = Table.grid(pad_edge=False)
            menu.add_column(width=3, justify="right")
            menu.add_column(width=20, overflow="fold")
            menu.add_column(width=3, justify="right")
            menu.add_column()
            for (n1, l1), (n2, l2) in zip(
                [(1, "🤖 Auto-Pilot"), (2, "📂 Profiles"),
                 (3, "🗂️  Groups"), (4, "📡 Subscriptions"),
                 (5, "⚙️  Settings"), (6, "⏹  Disconnect"),
                 (7, "📊 Dashboard")],
                [(8, "🛣️  Routing"), (9, "💻 OS Tools"),
                 (10, "💾 Backup/QR"), (11, "🔧 Dependencies"),
                 (12, "🌐 Psiphon Pilot"), (13, "🧙 Setup Wizard"),
                 (0, "Exit")]):
                menu.add_row(
                    f"[cyan]{n1:>2}[/cyan]", l1,
                    f"[cyan]{n2:>2}[/cyan]" if n2 else "[cyan] 0[/cyan]", l2)
            console.print(menu)

            active_subs = Settings.get("active_subscription_ids") or []
            active_groups = Settings.get("active_group_ids") or []
            if active_subs or active_groups:
                total_profiles = len(self._get_active_profiles())
                console.print(f"  [dim]📡 {len(active_subs)} subs · "
                              f"{len(active_groups)} groups · {total_profiles} profiles[/dim]")
            try:
                choice = Prompt.ask("Select", default="1",
                                    choices=[str(i) for i in range(0, 14)])
            except (EOFError, KeyboardInterrupt):
                break
            try:
                if choice == "0":
                    self.runner.stop()
                    self.watchdog.stop()
                    self.rotator.stop()
                    self.refresher.stop()
                    self.auto_refresher.stop()
                    break
                elif choice == "1":
                    self.auto_pilot()
                elif choice == "2":
                    self.profiles_menu()
                elif choice == "3":
                    self.groups_menu()
                elif choice == "4":
                    self.subscriptions_menu()
                elif choice == "5":
                    self.settings_menu()
                elif choice == "6":
                    self.runner.stop()
                    self.watchdog.stop()
                    self.rotator.stop()
                    console.print("[info]Disconnected.[/info]")
                    Sys.tts("Disconnected")
                elif choice == "7":
                    self.live_dashboard()
                elif choice == "8":
                    self.routing_menu()
                elif choice == "9":
                    self.os_tools_menu()
                elif choice == "10":
                    self.backup_menu()
                elif choice == "11":
                    self.dependencies_menu()
                elif choice == "12":
                    self.psiphon_auto_pilot()
                elif choice == "13":
                    self.setup_wizard()
            except Exception as e:
                console.print(
                    f"[fail]Action error: {type(e).__name__}: {rich_escape(str(e))}[/fail]")
                console.print(
                    f"[dim]{rich_escape(traceback.format_exc()[:1500])}[/dim]")
                logging.error(
                    f"main_menu action crash: {e}\n{traceback.format_exc()}")

    def live_dashboard(self):
        console.print(
            "[dim]Hotkeys are shown inside the dashboard panel.[/dim]")
        time.sleep(0.5)
        while True:
            action = self._run_dashboard_once()
            if action == "exit":
                break
            elif action == "best":
                best = self._find_best_profile()
                if best:
                    Settings.set("auto_switch_enabled", True)
                    self._do_connect(best, quiet=True)
                    console.print(
                        f"[success]Switched to best: {rich_escape(best['name'])} ({best['latency_ms']}ms)[/success]")
                    Sys.tts("Switched")
            elif action == "manual":
                self._connect_specific()
            elif action == "reping":
                self._reping_all_silent()
            elif action == "disconnect":
                self.runner.stop()
                self.watchdog.stop()
                self.rotator.stop()
                console.print("[info]Disconnected.[/info]")

    def _run_dashboard_once(self) -> str:
        action = "exit"
        listener = DashboardKeyListener()
        stop_worker = threading.Event()
        state = {"ping_ms": None}

        def _worker():
            last_ping = 0.0
            while not stop_worker.is_set():
                if self.runner.is_running():
                    now = time.time()
                    if now - last_ping > 3.0:
                        try:
                            p = self.runner.active_profile or {}
                            cfg = p.get("config", {}) or {}
                            host = (cfg.get("sni") or cfg.get("host_header")
                                    or cfg.get("address", "www.google.com"))
                            state["ping_ms"] = asyncio.run(real_ping_via_proxy(
                                str(host), 443,
                                int(Settings.get("socks_port", 10808)),
                                timeout=4.0))
                        except Exception:
                            state["ping_ms"] = None
                        last_ping = now
                else:
                    state["ping_ms"] = None
                    last_ping = 0.0
                stop_worker.wait(0.5)

        worker = threading.Thread(target=_worker, daemon=True)
        try:
            listener.start()
            worker.start()
            with Live(render_dashboard(self.runner, watchdog=self.watchdog, menu=self),
                      refresh_per_second=2, console=console) as live:
                while True:
                    key = listener.get(timeout=0.2)
                    if key:
                        if key in ('\r', '\n'):
                            action = "best"
                            break
                        elif key.lower() == 'p':
                            action = "manual"
                            break
                        elif key.lower() == 'r':
                            action = "reping"
                            break
                        elif key.lower() == 'd':
                            action = "disconnect"
                            break
                        elif key.lower() in ('q', '\x1b', '\x03'):
                            action = "exit"
                            break
                    live.update(render_dashboard(self.runner,
                                                 ping_ms=state["ping_ms"],
                                                 watchdog=self.watchdog, menu=self))
        except KeyboardInterrupt:
            action = "exit"
        finally:
            stop_worker.set()
            listener.stop()
        return action

    def _find_best_profile(self):
        profiles = self._get_active_profiles()
        usable = [p for p in profiles if p["protocol"] in (
            "vmess", "vless", "trojan", "ss", "socks", "hysteria2", "tuic",
            "shadowtls", "naive", "dnstt", "ssh", "psiphon", "tor", "wireguard")]
        if not usable:
            return None
        console.print("[info]Re-pinging active profiles...[/info]")
        with Progress(SpinnerColumn(), TextColumn("[cyan]Pinging..."), BarColumn(), console=console) as prog:
            task = prog.add_task("p", total=len(usable))
            asyncio.run(test_profiles_async(
                usable, on_progress=lambda: prog.advance(task)))
        profiles = self._get_active_profiles()
        healthy = [p for p in profiles if p.get("latency_ms") is not None]
        if not healthy:
            return None
        healthy.sort(key=lambda p: p["latency_ms"])
        return healthy[0]

    def _reping_all_silent(self):
        profiles = self._get_active_profiles()
        if not profiles:
            return
        console.print("[info]Re-pinging active profiles...[/info]")
        with Progress(SpinnerColumn(), TextColumn("[cyan]Pinging..."), BarColumn(), console=console) as prog:
            task = prog.add_task("p", total=len(profiles))
            asyncio.run(test_profiles_async(
                profiles, on_progress=lambda: prog.advance(task)))
        console.print("[success]Done.[/success]")
        time.sleep(0.6)

    def psiphon_auto_pilot(self):
        console.print(Rule("[title]🌐 Psiphon Auto-Pilot[/title]"))
        try:
            mode = Settings.get("psiphon_mode", "direct")
            console.print(f"[info]Mode: {mode}[/info]")
            if mode == "chain":
                profiles = self._get_active_profiles()
                usable = [p for p in profiles if p["protocol"] in
                          ("vmess", "vless", "trojan", "ss", "socks", "hysteria2")]
                if not usable:
                    console.print(
                        "[fail]No Xray profiles for chain. Falling back to direct.[/fail]")
                    mode = "direct"
                    Settings.set("psiphon_mode", "direct")
                else:
                    console.print(
                        f"[info]Testing {len(usable)} profiles for upstream...[/info]")
                    with Progress(SpinnerColumn(), TextColumn("[cyan]Testing..."), BarColumn(), console=console) as prog:
                        task = prog.add_task("test", total=len(usable))
                        asyncio.run(test_profiles_async(
                            usable, on_progress=lambda: prog.advance(task)))
                    profiles = self._get_active_profiles()
                    healthy = [p for p in profiles if p.get("latency_ms") is not None
                               and p["protocol"] in ("vmess", "vless", "trojan", "ss", "socks", "hysteria2")]
                    if not healthy:
                        console.print(
                            "[fail]No healthy Xray. Falling back to direct.[/fail]")
                        mode = "direct"
                        Settings.set("psiphon_mode", "direct")
                    else:
                        healthy.sort(key=lambda p: p["latency_ms"])
                        best_up = healthy[0]
                        Settings.set(
                            "psiphon_upstream_profile_id", best_up["id"])
                        console.print(
                            f"[success]Upstream: {rich_escape(best_up['name'])} ({best_up['latency_ms']}ms)[/success]")
            psiphon_profile = {
                "protocol": "psiphon",
                "name": f"Psiphon ({mode})",
                "config": {"region": Settings.get("psiphon_region", ""),
                           "config_url": Settings.get("psiphon_config_url", ""),
                           "local_socks_port": int(Settings.get("socks_port", 10808))}
            }
            ok = self.runner.launch(psiphon_profile)
            if ok:
                console.print(Panel(
                    f"[bold green]✓ Psiphon Connected ({mode})[/bold green]\n\n"
                    f"SOCKS5: [green]127.0.0.1:{Settings.get('socks_port')}[/green]\n"
                    f"HTTP:   [green]127.0.0.1:{Settings.get('http_port')}[/green]",
                    title="🌐 Psiphon Ready", border_style="green"))
                Sys.tts("Psiphon connected.")
                Sys.notify("Psiphon Connected", mode)
                console.print("[dim]Opening dashboard...[/dim]")
                time.sleep(0.5)
                self.live_dashboard()
            else:
                console.print("[fail]Psiphon failed.[/fail]")
                Sys.tts("Psiphon failed.")
        except Exception as e:
            console.print(
                f"[fail]Psiphon Auto-Pilot error: {type(e).__name__}: {rich_escape(str(e))}[/fail]")
            console.print(
                f"[dim]{rich_escape(traceback.format_exc()[:2000])}[/dim]")
            logging.error(
                f"psiphon_auto_pilot crash: {e}\n{traceback.format_exc()}")

    def groups_menu(self):
        while True:
            console.clear()
            console.print("\n[bold cyan]--- 🗂️ Groups ---[/bold cyan]")
            console.print("  1. List groups (with health)")
            console.print("  2. Create group")
            console.print("  3. Rename group")
            console.print("  4. Delete group")
            console.print("  5. Move profile to another group")
            console.print("  6. Set ACTIVE groups (filter)")
            console.print("  0. Back")
            c = Prompt.ask("Action", default="0", choices=[
                           "0", "1", "2", "3", "4", "5", "6"])
            if c == "0":
                break
            elif c == "1":
                self._pick_group(allow_create=False)
            elif c == "2":
                self._create_group()
            elif c == "3":
                gid = self._pick_group(allow_create=False)
                if not gid:
                    continue
                new = Prompt.ask("New name")
                if db.rename_group(gid, new):
                    console.print("[success]Renamed.[/success]")
                else:
                    console.print("[fail]Name taken.[/fail]")
            elif c == "4":
                gid = self._pick_group(allow_create=False)
                if not gid:
                    continue
                g = db.get_group(gid)
                if Confirm.ask(f"[red]Delete '{rich_escape(g['name'])}' and all profiles?[/red]", default=False):
                    db.delete_group(gid)
                    console.print("[success]Deleted.[/success]")
            elif c == "5":
                self._move_profile()
            elif c == "6":
                self._set_active_groups()
            _pause_for_output()

    def _set_active_groups(self):
        groups = db.list_groups()
        if not groups:
            console.print("[muted]No groups.[/muted]")
            return
        current = Settings.get("active_group_ids") or []
        console.print(
            "[info]Enter group numbers to ACTIVATE (comma-separated), or 'all' for all:[/info]")
        for i, g in enumerate(groups, 1):
            mark = "✓" if g["id"] in current else " "
            console.print(
                f"  [{mark}] {i}. {rich_escape(g['name'])} ({g['profile_count']} profiles)")
        raw = Prompt.ask("Active groups", default="all").strip()
        if raw.lower() == "all":
            Settings.set("active_group_ids", [])
            console.print("[success]All groups active.[/success]")
        else:
            try:
                ids = [groups[int(x.strip())-1]["id"]
                       for x in raw.split(",") if x.strip().isdigit()]
                Settings.set("active_group_ids", ids)
                console.print(f"[success]Active groups: {len(ids)}[/success]")
            except Exception:
                console.print("[fail]Invalid input.[/fail]")

    def _move_profile(self):
        profiles = db.list_profiles()
        if not profiles:
            console.print("[muted]No profiles.[/muted]")
            return
        for i, p in enumerate(profiles, 1):
            console.print(
                f"  {i}. [{p['protocol']}] {rich_escape(p['name'][:50])}")
        idx = IntPrompt.ask("Profile to move", choices=[
                            str(i) for i in range(1, len(profiles)+1)])
        target_gid = self._pick_group()
        if target_gid and target_gid != profiles[idx-1]["group_id"]:
            db.move_profile(profiles[idx-1]["id"], target_gid)
            console.print("[success]Moved.[/success]")

    def subscriptions_menu(self):
        while True:
            console.clear()
            console.print("\n[bold cyan]--- 📡 Subscriptions ---[/bold cyan]")
            console.print("  1. List subscriptions")
            console.print("  2. Add subscription URL")
            console.print("  3. Refresh subscription")
            console.print("  4. Refresh ALL")
            console.print("  5. Delete subscription")
            console.print("  6. Refresh all in a GROUP")
            console.print("  7. Import WireGuard .conf file")
            console.print("  8. Clear profiles (keep URL)")
            console.print("  9. Set ACTIVE subscriptions (filter)")
            console.print("  0. Back")
            c = Prompt.ask("Action", default="0", choices=[
                           "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"])
            if c == "0":
                break
            elif c == "1":
                self._list_subs()
            elif c == "2":
                self._add_sub()
            elif c == "3":
                self._refresh_sub(specific=True)
            elif c == "4":
                self._refresh_sub(specific=False)
            elif c == "5":
                self._delete_sub()
            elif c == "6":
                self._refresh_group()
            elif c == "7":
                self._import_wg_file()
            elif c == "8":
                self._clear_sub_profiles()
            elif c == "9":
                self._set_active_subs()
            _pause_for_output()

    def _set_active_subs(self):
        subs = db.list_subscriptions()
        if not subs:
            console.print("[muted]No subscriptions.[/muted]")
            return
        current = Settings.get("active_subscription_ids") or []
        console.print(
            "[info]Enter subscription numbers to ACTIVATE (comma-separated), or 'all':[/info]")
        for i, s in enumerate(subs, 1):
            mark = "✓" if s["id"] in current else " "
            console.print(
                f"  [{mark}] {i}. {rich_escape(s.get('name', '?'))} ({s['profile_count']} profiles)")
        raw = Prompt.ask("Active subscriptions", default="all").strip()
        if raw.lower() == "all":
            Settings.set("active_subscription_ids", [])
            console.print("[success]All subscriptions active.[/success]")
        else:
            try:
                ids = [subs[int(x.strip())-1]["id"]
                       for x in raw.split(",") if x.strip().isdigit()]
                Settings.set("active_subscription_ids", ids)
                console.print(
                    f"[success]Active subscriptions: {len(ids)}[/success]")
            except Exception:
                console.print("[fail]Invalid input.[/fail]")

    def _clear_sub_profiles(self):
        subs = db.list_subscriptions()
        if not subs:
            console.print("[muted]No subscriptions.[/muted]")
            return
        for i, s in enumerate(subs, 1):
            console.print(
                f"  {i}. {rich_escape(s.get('name', '?'))} — {s['profile_count']} profiles")
        idx = IntPrompt.ask("Clear which", choices=[
                            str(i) for i in range(1, len(subs)+1)])
        s = subs[idx-1]
        if Confirm.ask(f"[red]Delete all {s['profile_count']} profiles of '{rich_escape(s.get('name', '?'))}' (URL will be kept)?[/red]", default=False):
            n = db.clear_subscription_profiles(s["id"])
            console.print(
                f"[success]Cleared {n} profiles. URL preserved.[/success]")

    def _list_subs(self):
        subs = db.list_subscriptions()
        if not subs:
            console.print("[muted]No subscriptions.[/muted]")
            return
        groups = {g["id"]: g["name"] for g in db.list_groups()}
        active = Settings.get("active_subscription_ids") or []
        t = Table(title="Subscriptions")
        t.add_column("", width=2)
        t.add_column("#", width=3)
        t.add_column("Group")
        t.add_column("Name")
        t.add_column("URL", overflow="fold")
        t.add_column("Profiles", justify="right")
        t.add_column("Refresh(h)", justify="right")
        t.add_column("Last refresh")
        for i, s in enumerate(subs, 1):
            mark = "✓" if s["id"] in active else " " if active else "✓"
            t.add_row(mark, str(i), groups.get(s["group_id"], "?"),
                      (s.get("name") or "?")[:20],
                      s["url"][:40]+("..." if len(s["url"]) > 40 else ""),
                      str(s["profile_count"] or 0),
                      str(s.get("refresh_hours") or 8),
                      (s["last_refresh"] or "never")[:19])
        console.print(t)

    def _add_sub(self):
        gid = self._pick_group()
        if not gid:
            return
        url = Prompt.ask("Subscription URL").strip()
        if not url:
            return
        name = Prompt.ask("Label (optional)", default="").strip() or None
        default_hours = str(Settings.get("refresh_interval_hours", 8))
        hours_str = Prompt.ask(
            "Refresh every N hours (0=off)", default=default_hours)
        try:
            hours = int(float(hours_str))
        except ValueError:
            hours = 8
        sub_id = db.add_subscription(gid, url, name, refresh_hours=hours)
        console.print("[info]Fetching...[/info]")
        links = fetch_subscription(url)
        if not links:
            console.print("[fail]No links.[/fail]")
            return
        added = self._import_links(links, gid, sub_id)
        db.update_subscription(sub_id, added)
        console.print(
            f"[success]Added {added} profiles (refresh every {hours}h).[/success]")
        Sys.tts(f"Subscription added. {added} profiles.")
        Sys.notify("Subscription added", f"{added} profiles")
        if Settings.get("auto_connect_after_sub", True) and added > 0:
            if Confirm.ask("Connect to best profile now?", default=True):
                self.auto_pilot()

    def _refresh_sub(self, specific=True):
        subs = db.list_subscriptions()
        if not subs:
            console.print("[muted]No subscriptions.[/muted]")
            return
        if specific:
            for i, s in enumerate(subs, 1):
                console.print(f"  {i}. {s['url'][:60]}")
            idx = IntPrompt.ask(
                "Which", choices=[str(i) for i in range(1, len(subs)+1)])
            subs = [subs[idx-1]]
        total = 0
        for s in subs:
            console.print(f"\n[info]Refreshing: {s['url'][:60]}[/info]")
            links = fetch_subscription(s["url"])
            if not links:
                continue
            with db._txn() as c:
                c.execute(
                    "DELETE FROM profiles WHERE subscription_id=?", (s["id"],))
            added = self._import_links(links, s["group_id"], s["id"])
            db.update_subscription(s["id"], added)
            total += added
            console.print(f"[success]{added} profiles[/success]")
        if total:
            Sys.tts(f"Refreshed. {total} profiles.")
            Sys.notify("Refreshed", f"{total}")

    def _refresh_group(self):
        gid = self._pick_group(allow_create=False)
        if not gid:
            return
        subs = db.list_subscriptions(group_id=gid)
        if not subs:
            console.print("[muted]No subs in group.[/muted]")
            return
        total = 0
        for s in subs:
            links = fetch_subscription(s["url"])
            if not links:
                continue
            with db._txn() as c:
                c.execute(
                    "DELETE FROM profiles WHERE subscription_id=?", (s["id"],))
            added = self._import_links(links, s["group_id"], s["id"])
            db.update_subscription(s["id"], added)
            total += added
        console.print(f"[success]Total {total} refreshed.[/success]")
        Sys.notify("Group refreshed", f"{total} profiles")

    def _delete_sub(self):
        subs = db.list_subscriptions()
        if not subs:
            return
        for i, s in enumerate(subs, 1):
            console.print(f"  {i}. {s['url'][:60]}")
        idx = IntPrompt.ask(
            "Which", choices=[str(i) for i in range(1, len(subs)+1)])
        if Confirm.ask("[red]Delete subscription and its profiles?[/red]", default=False):
            with db._txn() as c:
                c.execute("DELETE FROM profiles WHERE subscription_id=?",
                          (subs[idx-1]["id"],))
            db.delete_subscription(subs[idx-1]["id"])
            console.print("[success]Deleted.[/success]")

    def _import_wg_file(self):
        gid = self._pick_group()
        if not gid:
            return
        path = Path(Prompt.ask("Path to .conf").strip()).expanduser()
        if not path.exists():
            console.print("[fail]Not found.[/fail]")
            return
        parsed = parse_wireguard_conf_file(path)
        if not parsed:
            console.print("[fail]Invalid WG config.[/fail]")
            return
        raw = f"wireguard://file://{path.resolve()}"
        pid = db.add_profile(gid, None, "wireguard",
                             parsed["name"], raw, parsed["config"])
        if pid:
            console.print(
                f"[success]Imported '{rich_escape(parsed['name'])}'[/success]")
        else:
            console.print("[fail]Add failed.[/fail]")

    def profiles_menu(self):
        while True:
            console.clear()
            console.print("\n[bold cyan]--- 📂 Profiles ---[/bold cyan]")
            console.print("  1. List profiles")
            console.print("  2. Add single link")
            console.print("  3. Add bulk (paste)")
            console.print("  4. Test all (TCPing)")
            console.print(
                "  5. Connect to specific profile  [disables auto-switch]")
            console.print("  6. Delete profile")
            console.print("  7. Real-ping through running proxy")
            console.print("  8. Speed test through running proxy")
            console.print("  9. Export profile to QR")
            console.print(" 10. Import from QR / clipboard")
            console.print(" 11. Add Psiphon (auto)")
            console.print("  0. Back")
            c = Prompt.ask("Action", default="0", choices=[
                           str(i) for i in range(0, 12)])
            if c == "0":
                break
            elif c == "1":
                self._list_profiles()
            elif c == "2":
                self._add_single()
            elif c == "3":
                self._add_bulk()
            elif c == "4":
                self._test_all()
            elif c == "5":
                self._connect_specific()
            elif c == "6":
                self._delete_profile()
            elif c == "7":
                self._real_ping_menu()
            elif c == "8":
                self._speed_test_menu()
            elif c == "9":
                self._qr_export_menu()
            elif c == "10":
                qr_import()
            elif c == "11":
                self._add_psiphon()
            _pause_for_output()

    def _add_psiphon(self):
        gid = self._pick_group()
        if not gid:
            return
        region = Prompt.ask("Psiphon region (empty=auto)",
                            default=Settings.get("psiphon_region", ""))
        Settings.set("psiphon_region", region)
        raw = f"psiphon://?region={region}&socks_port={Settings.get('socks_port', 10808)}"
        cfg = {"region": region, "config_url": "", "local_socks_port": int(
            Settings.get("socks_port", 10808)), "extra_args": ""}
        pid = db.add_profile(gid, None, "psiphon",
                             f"Psiphon ({region or 'auto'})", raw, cfg)
        if pid:
            console.print(f"[success]Psiphon profile added.[/success]")
        else:
            console.print("[fail]Add failed.[/fail]")

    def _list_profiles(self, group_id=None):
        profiles = db.list_profiles(group_id=group_id)
        if not profiles:
            console.print("[muted]No profiles.[/muted]")
            return
        groups = {g["id"]: g["name"] for g in db.list_groups()}
        t = Table(title=f"Profiles ({len(profiles)})")
        t.add_column("#", width=3)
        t.add_column("Group", width=10)
        t.add_column("Name", overflow="ellipsis", max_width=22)
        t.add_column("Proto", width=8)
        t.add_column("Latency", justify="right", width=9)
        t.add_column("Real", justify="right", width=8)
        t.add_column("Speed", justify="right", width=8)
        t.add_column("Status", width=10)
        for i, p in enumerate(profiles, 1):
            color = {"healthy": "green", "unhealthy": "red"}.get(
                p["status"], "dim")
            lat = f"{p['latency_ms']} ms" if p["latency_ms"] is not None else "—"
            real = f"{p['real_ping_ms']} ms" if p.get(
                "real_ping_ms") is not None else "—"
            spd = f"{p['speed_kbps']:.0f} KB/s" if p.get("speed_kbps") else "—"
            t.add_row(str(i), groups.get(p["group_id"], "?"),
                      p["name"][:22] if p["name"] else "?", p["protocol"],
                      lat, real, spd, f"[{color}]{p['status']}[/]")
        console.print(t)

    def _add_single(self):
        gid = self._pick_group()
        if not gid:
            return
        link = Prompt.ask("Paste link")
        parsed = URLParser.parse(link.strip())
        if not parsed:
            console.print("[fail]Could not parse.[/fail]")
            return
        pid = db.add_profile(gid, None, parsed["protocol"], parsed["name"],
                             link.strip(), parsed["config"])
        if pid:
            console.print(
                f"[success]Added: {rich_escape(parsed['name'])} ({parsed['protocol']})[/success]")
            Sys.tts("Profile added")
        else:
            console.print("[fail]Duplicate or error.[/fail]")

    def _add_bulk(self):
        gid = self._pick_group()
        if not gid:
            return
        console.print(
            "[info]Paste links, one per line. Empty line to finish.[/info]")
        lines = []
        while True:
            try:
                ln = input()
            except EOFError:
                break
            if not ln.strip():
                break
            lines.append(ln.strip())
        if not lines:
            console.print("[warn]None.[/warn]")
            return
        added = self._import_links(lines, gid)
        console.print(f"[success]Imported {added}/{len(lines)}.[/success]")
        Sys.tts(f"Imported {added}.")
        Sys.notify("Bulk", f"{added}")

    def _test_all(self):
        profiles = self._get_active_profiles()
        if not profiles:
            console.print("[muted]No profiles.[/muted]")
            return
        if not battery_ok():
            console.print("[warn]Battery low — reducing concurrency.[/warn]")
        console.print(
            f"[info]Testing {len(profiles)} active profiles...[/info]")
        with Progress(SpinnerColumn(), TextColumn("[cyan]Testing..."), BarColumn(), console=console) as prog:
            task = prog.add_task("test", total=len(profiles))
            asyncio.run(test_profiles_async(
                profiles, on_progress=lambda: prog.advance(task)))
        healthy = sum(1 for p in profiles if p["latency_ms"] is not None)
        console.print(
            f"[success]{healthy}/{len(profiles)} reachable[/success]")
        Sys.tts(f"Test complete. {healthy} reachable.")

    def _real_ping_menu(self):
        if not self.runner.is_running():
            console.print("[warn]Connect first.[/warn]")
            return
        profiles = db.list_profiles()
        socks = int(Settings.get("socks_port", 10808))

        async def run():
            for p in profiles:
                cfg = p.get("config", {})
                host = cfg.get("sni") or cfg.get(
                    "host_header") or cfg.get("address", "www.google.com")
                ms = await real_ping_via_proxy(str(host), 443, socks, timeout=6.0)
                with db._txn() as c:
                    c.execute(
                        "UPDATE profiles SET real_ping_ms=? WHERE id=?", (ms, p["id"]))
                color = "green" if (ms and ms < 300) else (
                    "yellow" if ms else "red")
                console.print(
                    f"  [{color}]{rich_escape(p['name'][:40]):40s} {str(ms) if ms else '—'} ms[/{color}]")
        asyncio.run(run())

    def _speed_test_menu(self):
        if not self.runner.is_running():
            console.print("[warn]Connect first.[/warn]")
            return
        socks = int(Settings.get("socks_port", 10808))
        console.print(
            "[info]Running 5MB download speed test via proxy...[/info]")
        kbps = asyncio.run(speed_test_via_proxy(socks))
        if kbps:
            console.print(f"[success]Speed: {kbps:.1f} KB/s[/success]")
            Sys.notify("Speed test", f"{kbps:.0f} KB/s")
            if self.runner.active_profile:
                db.update_profile_latency(self.runner.active_profile["id"],
                                          self.runner.active_profile.get(
                                              "latency_ms"),
                                          speed_kbps=kbps)
        else:
            console.print("[fail]Speed test failed.[/fail]")

    def _qr_export_menu(self):
        profiles = db.list_profiles()
        if not profiles:
            console.print("[muted]No profiles.[/muted]")
            return
        for i, p in enumerate(profiles, 1):
            console.print(
                f"  {i}. [{p['protocol']}] {rich_escape(p['name'][:40])}")
        idx = IntPrompt.ask("Export which", choices=[
                            str(i) for i in range(1, len(profiles)+1)])
        qr_export(profiles[idx-1])

    def _connect_specific(self):
        profiles = self._get_active_profiles()
        usable = [p for p in profiles if p["protocol"] in
                  ("vmess", "vless", "trojan", "ss", "socks", "hysteria2", "tuic",
                   "shadowtls", "naive", "dnstt", "ssh", "psiphon", "tor", "wireguard")]
        if not usable:
            console.print("[fail]No supported profiles.[/fail]")
            return
        page_size = 10
        total_pages = max(1, (len(usable) + page_size - 1) // page_size)
        page = 0
        while True:
            start = page * page_size
            chunk = usable[start:start + page_size]
            table = Table(title=f"Pick a profile  (page {page + 1}/{total_pages})",
                          box=box.SIMPLE_HEAVY)
            table.add_column("#", justify="right", style="cyan", width=4)
            table.add_column("Name", style="white")
            table.add_column("Type", style="dim", width=10)
            table.add_column("Ping", justify="right", width=8)
            for i, p in enumerate(chunk):
                num = start + i + 1
                lat = (f"{p['latency_ms']} ms"
                       if p["latency_ms"] is not None else "—")
                table.add_row(str(num), rich_escape(p["name"][:40]),
                              p["protocol"], lat)
            console.print(table)
            choices = [str(n) for n in range(start + 1, start + len(chunk) + 1)]
            nav = []
            if page > 0:
                nav.append("b=back")
            if page < total_pages - 1:
                nav.append("n=next")
            nav.append("q=cancel")
            try:
                c = Prompt.ask("Pick number or " + "  ".join(nav),
                               default="q", choices=choices + ["n", "b", "q"],
                               show_choices=False)
            except (KeyboardInterrupt, EOFError):
                return
            if c == "q":
                return
            if c == "n":
                page = min(page + 1, total_pages - 1)
                continue
            if c == "b":
                page = max(page - 1, 0)
                continue
            try:
                idx = int(c) - 1
            except ValueError:
                continue
            if 0 <= idx < len(usable):
                Settings.set("auto_switch_enabled", False)
                console.print(
                    "[warn]Auto-switch DISABLED (manual selection). Use Auto-Pilot or Dashboard Enter to re-enable.[/warn]")
                self._do_connect(usable[idx])
                return

    def _delete_profile(self):
        profiles = db.list_profiles()
        if not profiles:
            return
        for i, p in enumerate(profiles, 1):
            console.print(
                f"  {i}. [{p['protocol']}] {rich_escape(p['name'][:50])}")
        idx = IntPrompt.ask("Delete which", choices=[
                            str(i) for i in range(1, len(profiles)+1)])
        db.delete_profile(profiles[idx-1]["id"])
        console.print("[success]Deleted.[/success]")

    def auto_pilot(self):
        console.print(Rule("[title]🤖 Auto-Pilot[/title]"))
        try:
            profiles = self._get_active_profiles()
            if not profiles:
                console.print("[warn]No profiles.[/warn]")
                return
            usable = [p for p in profiles if p["protocol"] in
                      ("vmess", "vless", "trojan", "ss", "socks", "hysteria2", "tuic",
                       "shadowtls", "naive", "dnstt", "ssh", "psiphon", "tor", "wireguard")]
            if not usable:
                console.print("[fail]No supported profiles.[/fail]")
                return
            console.print(
                f"[info]Testing {len(usable)} active profiles...[/info]")
            with Progress(SpinnerColumn(), TextColumn("[cyan]Testing..."), BarColumn(), console=console) as prog:
                task = prog.add_task("test", total=len(usable))
                asyncio.run(test_profiles_async(
                    usable, on_progress=lambda: prog.advance(task)))
            profiles = self._get_active_profiles()
            healthy = [p for p in profiles if p["latency_ms"] is not None]
            if not healthy:
                console.print("[fail]No reachable.[/fail]")
                Sys.tts("No reachable.")
                return
            healthy.sort(key=lambda p: p["latency_ms"])
            best = healthy[0]
            console.print(
                f"[success]Best: {rich_escape(best['name'])} — {best['latency_ms']} ms[/success]")
            Settings.set("auto_switch_enabled", True)
            extra = None
            if Settings.get("load_balancing", False) and len(healthy) > 1:
                extra = healthy[1:5]
            self._do_connect(best, extra_proxies=extra)
        except Exception as e:
            console.print(
                f"[fail]Auto-Pilot error: {type(e).__name__}: {rich_escape(str(e))}[/fail]")
            console.print(
                f"[dim]{rich_escape(traceback.format_exc()[:2000])}[/dim]")
            logging.error(f"auto_pilot crash: {e}\n{traceback.format_exc()}")

    def _do_connect(self, profile: Dict, extra_proxies: List[Dict] = None, quiet: bool = False):
        if not quiet:
            console.print(
                f"[info]Connecting to {rich_escape(profile['name'])}...[/info]")
        ok = False
        try:
            ok = self.runner.launch(profile, extra_proxies=extra_proxies)
        except Exception as e:
            console.print(
                f"[fail]Connection error: {type(e).__name__}: {rich_escape(str(e))}[/fail]")
            console.print(
                f"[dim]{rich_escape(traceback.format_exc()[:2000])}[/dim]")
            logging.error(f"_do_connect crash: {e}\n{traceback.format_exc()}")
            return
        if ok:
            if not quiet:
                console.print(Panel(
                    f"[bold green]✓ Connected[/bold green]\n\n"
                    f"Profile: [cyan]{rich_escape(profile['name'])}[/cyan]\n"
                    f"Proto:   [cyan]{profile['protocol']}[/cyan]\n"
                    f"Core:    [cyan]{self.runner.active_kind}[/cyan]\n"
                    f"SOCKS5:  [green]127.0.0.1:{Settings.get('socks_port')}[/green]\n"
                    f"HTTP:    [green]127.0.0.1:{Settings.get('http_port')}[/green]",
                    title="🌐 Proxy Ready", border_style="green"))
            lat = profile.get("latency_ms")
            lat_s = f"{lat}ms" if lat else "?"
            Sys.tts(f"Connected. {lat_s}.")
            Sys.notify("Connected", f"{profile['name']} ({lat_s})")
            Sys.vibrate(200)
            if Settings.get("torch_on_connect", False):
                Sys.torch(True, int(Settings.get("torch_duration_ms", 1000)))
            if Settings.get("failover", False):
                self.watchdog.start()
            if float(Settings.get("auto_rotate_minutes", 0) or 0) > 0:
                self.rotator.start()
        else:
            if not quiet:
                console.print("[fail]Failed.[/fail]")
                Sys.tts("Failed.")
                Sys.vibrate(500)

    def routing_menu(self):
        while True:
            console.clear()
            console.print("\n[bold cyan]--- 🛣️ Routing Rules ---[/bold cyan]")
            console.print(
                f"  1. Bypass China          : {'ON' if Settings.get('china_bypass') else 'OFF'}")
            console.print(
                f"  2. Bypass Russia         : {'ON' if Settings.get('russia_bypass') else 'OFF'}")
            console.print(
                f"  3. Random Subdomain (WS) : {'ON' if Settings.get('random_subdomain') else 'OFF'}")
            console.print(
                f"  4. Load Balancing        : {'ON' if Settings.get('load_balancing') else 'OFF'}")
            console.print(
                f"  5. Iran IP bypass (GeoIP+Range) : {'ON' if Settings.get('iran_ip_bypass') else 'OFF'}")
            console.print("  6. Add custom rule (domain → direct)")
            console.print("  7. Add custom rule (IP/CIDR → direct)")
            console.print("  8. Clear custom rules")
            console.print("  9. List custom rules")
            console.print("  0. Back")
            c = Prompt.ask("Action", default="0", choices=[
                           "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"])
            if c == "0":
                break
            elif c == "1":
                Settings.set("china_bypass", not Settings.get("china_bypass"))
                console.print("[success]Toggled.[/success]")
            elif c == "2":
                Settings.set("russia_bypass",
                             not Settings.get("russia_bypass"))
                console.print("[success]Toggled.[/success]")
            elif c == "3":
                Settings.set("random_subdomain",
                             not Settings.get("random_subdomain"))
                console.print("[success]Toggled.[/success]")
            elif c == "4":
                Settings.set("load_balancing",
                             not Settings.get("load_balancing"))
                console.print("[success]Toggled.[/success]")
            elif c == "5":
                Settings.set("iran_ip_bypass",
                             not Settings.get("iran_ip_bypass"))
                console.print("[success]Toggled.[/success]")
            elif c == "6":
                d = Prompt.ask("Domain (e.g. example.com)")
                rules = Settings.get("custom_routing_rules", [])
                rules.append({"type": "field", "domain": [
                             f"domain:{d}"], "outboundTag": "direct"})
                Settings.set("custom_routing_rules", rules)
                console.print("[success]Added.[/success]")
            elif c == "7":
                ip = Prompt.ask("IP or CIDR")
                rules = Settings.get("custom_routing_rules", [])
                rules.append({"type": "field", "ip": [
                             ip], "outboundTag": "direct"})
                Settings.set("custom_routing_rules", rules)
                console.print("[success]Added.[/success]")
            elif c == "8":
                Settings.set("custom_routing_rules", [])
                console.print("[success]Cleared.[/success]")
            elif c == "9":
                rules = Settings.get("custom_routing_rules", [])
                if not rules:
                    console.print("[muted]None.[/muted]")
                else:
                    console.print(
                        Panel(json.dumps(rules, indent=2), title="Custom Rules"))
            _pause_for_output()

    def os_tools_menu(self):
        os_name = PLATFORM["os"]
        os_label = {"windows": "🪟 Windows", "linux": "🐧 Linux",
                    "macos": "🍎 macOS", "android": "🤖 Android/Termux",
                    "bsd": " BSD"}.get(os_name, os_name)
        while True:
            console.clear()
            console.print(
                f"\n[bold cyan]--- 💻 OS Tools ({os_label}) ---[/bold cyan]")
            items = [
                ("1", "Battery status"),
                ("2", f"Toggle battery-aware mode : "
                 f"{'ON' if Settings.get('battery_aware') else 'OFF'}"),
                ("3", f"Toggle screen-off mode     : "
                 f"{'ON' if Settings.get('screen_off_aware') else 'OFF'}"),
                ("4", "Copy text to clipboard"),
                ("5", "Paste from clipboard"),
                ("6", "Send test notification"),
                ("7", "Speak test message (TTS)"),
                ("8", "Flush DNS cache"),
                ("9", "Open data folder"),
            ]
            if TERMUX:
                items += [
                    ("10", "Setup storage (termux-setup-storage)"),
                    ("11", f"Toggle torch on connect : "
                     f"{'ON' if Settings.get('torch_on_connect') else 'OFF'}"),
                    ("12", "Flash torch now"),
                    ("13", "Generate Termux:Widget helper script"),
                ]
            for n, label in items:
                console.print(f"  {n:>2}. {label}")
            console.print("   0. Back")
            valid = [n for n, _ in items] + ["0"]
            c = Prompt.ask("Action", default="0", choices=valid)
            if c == "0":
                break
            elif c == "1":
                bat = Sys.battery()
                plugged = bat.get("plugged", "?")
                console.print(
                    Panel(
                        f"Level   : {bat.get('percentage', '?')}%\n"
                        f"Plugged : {plugged}",
                        title="Battery"))
            elif c == "2":
                Settings.set("battery_aware",
                             not Settings.get("battery_aware"))
                console.print("[success]Toggled.[/success]")
            elif c == "3":
                Settings.set("screen_off_aware",
                             not Settings.get("screen_off_aware"))
                console.print("[success]Toggled.[/success]")
            elif c == "4":
                txt = Prompt.ask("Text to copy")
                if Sys.clipboard_set(txt):
                    console.print("[success]Copied.[/success]")
                else:
                    console.print(
                        "[warn]Clipboard not available on this platform "
                        "(needs Termux:API / xclip / wl-clipboard).[/warn]")
            elif c == "5":
                txt = Sys.clipboard_get()
                console.print(
                    Panel(txt or "[muted]empty[/muted]", title="Clipboard"))
            elif c == "6":
                Sys.notify("MultiProxy", "Test notification")
                console.print("[success]Notification sent.[/success]")
            elif c == "7":
                Sys.tts("MultiProxy test message")
                console.print("[success]Spoken (if TTS available).[/success]")
            elif c == "8":
                if Sys.flush_dns():
                    console.print("[success]DNS cache flushed.[/success]")
                else:
                    console.print(
                        "[warn]No supported DNS flush method found.[/warn]")
            elif c == "9":
                self._open_data_folder()
            elif c == "10":
                if Sys.setup_storage():
                    console.print(
                        "[success]Storage setup triggered.[/success]")
                else:
                    console.print("[warn]Only on Termux.[/warn]")
            elif c == "11":
                Settings.set("torch_on_connect",
                             not Settings.get("torch_on_connect"))
                console.print("[success]Toggled.[/success]")
            elif c == "12":
                Sys._run(["termux-torch", "on"])
                time.sleep(1)
                Sys._run(["termux-torch", "off"])
                console.print("[success]Flashed.[/success]")
            elif c == "13":
                self._write_widget_helper()
            _pause_for_output()

    def _open_data_folder(self):
        target = SCRIPT_DIR
        os_name = PLATFORM["os"]
        try:
            if os_name == "windows":
                os.startfile(target)  # noqa: S606
            elif os_name == "macos":
                subprocess.Popen(["open", str(target)])
            elif shutil.which("xdg-open"):
                subprocess.Popen(["xdg-open", str(target)])
            else:
                console.print(f"[info]{target}[/info]")
                return
            console.print(f"[success]Opened: {target}[/success]")
        except Exception as e:
            console.print(f"[fail]Could not open folder: {e}[/fail]")

    def _write_widget_helper(self):
        if not TERMUX:
            console.print("[warn]Only on Termux.[/warn]")
            return
        shortcut_dir = Path.home() / ".shortcuts" / "MultiProxy"
        shortcut_dir.mkdir(parents=True, exist_ok=True)
        script = shortcut_dir / "autopilot.sh"
        script.write_text(f"""#!/data/data/com.termux/files/usr/bin/bash
cd {SCRIPT_DIR}
python {Path(__file__).name} --autopilot
""")
        script.chmod(0o755)
        console.print(f"[success]Widget helper: {script}[/success]")
        console.print(
            "[dim]Add 'MultiProxy' folder to Termux:Widget on your home screen.[/dim]")

    def backup_menu(self):
        while True:
            console.clear()
            console.print(
                "\n[bold cyan]--- 💾 Backup / Restore / QR ---[/bold cyan]")
            console.print("  1. Create backup (ZIP)")
            console.print("  2. Restore from ZIP")
            console.print("  3. List backups")
            console.print("  0. Back")
            c = Prompt.ask("Action", default="0", choices=["0", "1", "2", "3"])
            if c == "0":
                break
            elif c == "1":
                create_backup()
            elif c == "2":
                path = Path(Prompt.ask("Path to .zip").strip()).expanduser()
                restore_backup(path)
            elif c == "3":
                backups = sorted(BACKUP_DIR.glob("*.zip"), reverse=True)
                if not backups:
                    console.print("[muted]None.[/muted]")
                else:
                    for b in backups[:20]:
                        console.print(
                            f"  - {b.name} ({b.stat().st_size//1024} KB)")
            _pause_for_output()

    def _settings_category(self, title: str, items: list):
        """items: (key, label, kind, extra) — kind: bool/int/float/str/choice."""
        s = Settings
        while True:
            t = Table(title=title, box=box.SIMPLE, expand=False)
            t.add_column("#", style="cyan", width=3, justify="right")
            t.add_column("Setting", min_width=24)
            t.add_column("Value", min_width=18, overflow="fold")
            for i, (key, label, kind, extra) in enumerate(items, 1):
                v = s.get(key)
                if kind == "bool":
                    shown = "[green]ON[/green]" if v else "[red]OFF[/red]"
                elif kind == "float":
                    shown = f"{v:g}" if isinstance(v, (int, float)) else str(v)
                else:
                    shown = str(v) if v not in (None, "") else "—"
                t.add_row(str(i), label, shown)
            console.print(t)
            c = Prompt.ask("Edit # (0=back)", default="0")
            if c == "0":
                break
            if not (c.isdigit() and 1 <= int(c) <= len(items)):
                console.print("[fail]Invalid.[/fail]")
                continue
            key, label, kind, extra = items[int(c)-1]
            try:
                if kind == "bool":
                    s.set(key, not s.get(key, True))
                elif kind == "int":
                    v = IntPrompt.ask(label, default=s.get(key))
                    s.set(key, max(extra.get("min", -(2**31)),
                          min(extra.get("max", 2**31), v)))
                elif kind == "float":
                    v = float(Prompt.ask(label, default=str(s.get(key))))
                    s.set(key, v)
                elif kind == "choice":
                    s.set(key, Prompt.ask(
                        label, choices=extra["choices"], default=s.get(key)))
                else:
                    s.set(key, Prompt.ask(label, default=s.get(key) or ""))
                console.print(f"[success]{key} = {s.get(key)}[/success]")
            except (ValueError, TypeError):
                console.print("[fail]Invalid value.[/fail]")

    def settings_menu(self):
        while True:
            console.clear()
            console.print(Rule("[title]⚙️ Settings[/title]"))
            console.print("  [cyan]1[/cyan]. 🌐 Network & Ports")
            console.print("  [cyan]2[/cyan]. 🛣️  Routing & DPI")
            console.print("  [cyan]3[/cyan]. 🤖 Automation")
            console.print("  [cyan]4[/cyan]. 🌐 Psiphon")
            console.print("  [cyan]5[/cyan]. 📱 Interface & Device")
            console.print("  [cyan]6[/cyan]. 🔬 Advanced")
            console.print("  [cyan]0[/cyan]. Back")
            c = Prompt.ask("Category", default="0", choices=[
                           "0", "1", "2", "3", "4", "5", "6"])
            if c == "0":
                break
            elif c == "1":
                self._settings_category("Network & Ports", [
                    ("socks_port", "SOCKS5 port",
                     "int", {"min": 1, "max": 65535}),
                    ("socks_port_2", "SOCKS5 port 2 (chain)",
                     "int", {"min": 1, "max": 65535}),
                    ("http_port", "HTTP port", "int",
                     {"min": 1, "max": 65535}),
                    ("dns", "DNS server", "str", {}),
                    ("concurrency", "Test concurrency",
                     "int", {"min": 1, "max": 200}),
                    ("timeout", "Ping timeout (s)", "float", {}),
                ])
            elif c == "2":
                self._settings_category("Routing & DPI", [
                    ("routing", "Routing preset", "choice",
                     {"choices": ["bypass_iran", "bypass_lan", "proxy_all"]}),
                    ("fragment", "Fragment (DPI bypass)", "bool", {}),
                    ("fragment_length", "Fragment length", "str", {}),
                    ("fragment_interval", "Fragment interval", "str", {}),
                    ("mux", "Mux multiplexing", "bool", {}),
                    ("mux_concurrency", "Mux concurrency",
                     "int", {"min": 1, "max": 128}),
                    ("geosite_ads_block", "Block ads (geosite)", "bool", {}),
                    ("load_balancing", "Load balancing", "bool", {}),
                    ("lb_strategy", "LB strategy", "choice",
                     {"choices": ["leastPing", "roundRobin", "random"]}),
                ])
            elif c == "3":
                self._settings_category("Automation", [
                    ("auto_switch_enabled", "Auto-switch to best", "bool", {}),
                    ("failover", "Watchdog failover", "bool", {}),
                    ("failover_interval_sec", "Failover interval (s)",
                     "int", {"min": 5, "max": 3600}),
                    ("failover_max_fails", "Failover max fails",
                     "int", {"min": 1, "max": 50}),
                    ("auto_rotate_minutes", "Auto-rotate (min, 0=off)", "float", {}),
                    ("auto_connect_after_sub",
                     "Auto-connect after sub add", "bool", {}),
                    ("auto_refresh_profiles_minutes",
                     "Profile auto-refresh (min)", "float", {}),
                    ("refresh_interval_hours", "Sub refresh (h)", "float", {}),
                    ("auto_install", "Auto-install dependencies", "bool", {}),
                ])
            elif c == "4":
                self._settings_category("Psiphon", [
                    ("psiphon_mode", "Mode", "choice", {
                     "choices": ["direct", "chain", "dns"]}),
                    ("psiphon_region", "Region (empty=auto)", "str", {}),
                    ("psiphon_config_url", "Config URL", "str", {}),
                    ("psiphon_upstream_profile_id", "Upstream profile ID",
                     "int", {"min": 0, "max": 2**31}),
                    ("psiphon_dns_source", "DNS source (URL/file)", "str", {}),
                    ("psiphon_use_dns", "Use Psiphon DNS", "bool", {}),
                    ("safe_launch_retries", "Safe launch retries",
                     "int", {"min": 1, "max": 5}),
                ])
            elif c == "5":
                self._settings_category("Interface & Device", [
                    ("tts", "Text-to-speech", "bool", {}),
                    ("notify", "Notifications", "bool", {}),
                    ("vibrate", "Vibration (Termux)", "bool", {}),
                    ("battery_aware", "Battery-aware mode", "bool", {}),
                    ("battery_threshold", "Battery threshold %",
                     "int", {"min": 5, "max": 95}),
                    ("screen_off_aware", "Screen-off aware", "bool", {}),
                    ("torch_on_connect", "Torch on connect", "bool", {}),
                ])
            elif c == "6":
                self._settings_category("Advanced", [
                    ("xray_test_before_launch", "Xray -test pre-check", "bool", {}),
                    ("audit_enabled", "Audit log", "bool", {}),
                    ("sqlcipher_key", "SQLCipher key (empty=off)", "str", {}),
                ])
            _pause_for_output()


def _tts_available() -> bool:
    if TERMUX and shutil.which("termux-tts-speak"):
        return True
    if PLATFORM["os"] == "windows":
        return True  # SAPI is built into Windows
    if shutil.which("espeak") or shutil.which("say") or shutil.which("spd-say"):
        return True
    return False


def _check_environment():
    if TERMUX:
        console.print(f"[info]Termux detected (PREFIX={TERMUX_PREFIX})[/info]")
    rows = []
    for name, f in [("Xray", find_xray), ("Hysteria2", find_hysteria), ("wg-quick", find_wg_quick),
                    ("sing-box", find_singbox), ("dnstt-client", find_dnstt),
                    ("psiphon", find_psiphon), ("tor", find_tor)]:
        p = f()
        rows.append(
            (name, f"[green]✓ {p}[/green]" if p else "[red]✗ missing[/red]"))
    if not _tts_available():
        rows.append(("TTS", "[red]✗ missing[/red]"))
    else:
        rows.append(("TTS", "[green]✓[/green]"))
    rows.append(
        ("QR", "[green]✓[/green]" if _HAS_QR else "[red]✗ missing[/red]"))
    t = Table(title="Environment", box=box.SIMPLE, expand=False)
    t.add_column("Component", style="bold", min_width=14)
    t.add_column("Status", min_width=20, overflow="fold")
    for name, status in rows:
        t.add_row(name, status)
    console.print(t)
    if not _tts_available():
        console.print(
            "[dim]No TTS engine. Install termux-api or espeak.[/dim]")
    if not _HAS_QR:
        console.print("[dim]Install `qrcode[pil]` for QR support.[/dim]")
    if _HAS_SQLCIPHER and Settings.get("sqlcipher_key"):
        console.print("[success]SQLCipher active (encrypted DB).[/success]")
    elif Settings.get("sqlcipher_key") and not _HAS_SQLCIPHER:
        console.print(
            "[warn]SQLCipher key set but sqlcipher3 not installed.[/warn]")


def main():
    Settings.load()
    global db
    db = DB()
    DependencyManager.ensure_all()
    _check_environment()
    menu = Menu()
    menu.refresher.start()
    menu.auto_refresher.start()
    try:
        if not db.list_profiles() and not db.list_subscriptions():
            console.print(
                "[info]First run detected — starting setup wizard.[/info]")
            menu.setup_wizard()
    except Exception as e:
        console.print(
            f"[warn]Wizard skipped: {type(e).__name__}: {rich_escape(str(e))}[/warn]")
    exit_code = 0
    try:
        menu.main_menu()
    except KeyboardInterrupt:
        console.print("\n[warn]Interrupted.[/warn]")
    except SystemExit:
        pass
    except Exception as e:
        console.print(
            f"\n[fail]Unhandled error: {type(e).__name__}: {rich_escape(str(e))}[/fail]")
        console.print(
            f"[dim]{rich_escape(traceback.format_exc()[:3000])}[/dim]")
        logging.error(f"main crash: {e}\n{traceback.format_exc()}")
        exit_code = 1
    finally:
        try:
            menu.runner.stop()
            menu.watchdog.stop()
            menu.rotator.stop()
            menu.refresher.stop()
            menu.auto_refresher.stop()
        except Exception as e:
            logging.error("main() shutdown cleanup failed: %s\n%s",
                          e, traceback.format_exc())
    sys.exit(exit_code)


db: Optional[DB] = None
if __name__ == "__main__":
    main()
