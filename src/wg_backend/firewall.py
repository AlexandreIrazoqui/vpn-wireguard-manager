# src/wg_backend/firewall.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from .wireguard import run_cmd, _which


# -----------------------------
# Data
# -----------------------------

@dataclass
class FirewallResult:
    wan_iface: str
    backend: str = "iptables"
    input_udp: bool = False
    forward_wg_to_wan: bool = False
    forward_established: bool = False
    nat_masquerade: bool = False
    notes: str = ""


# -----------------------------
# Low-level helpers
# -----------------------------

CH_IN = "VPNWG_IN"
CH_FWD = "VPNWG_FWD"
CH_NAT = "VPNWG_NAT"


def _is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def detect_wan_iface() -> str:
    _which("ip")
    out = run_cmd(["ip", "route", "show", "default"], check=True).stdout.strip()
    line = next((l for l in out.splitlines() if l.strip()), "")
    if not line:
        raise RuntimeError("Cannot detect default route (no 'ip route show default' output).")
    parts = line.split()
    if "dev" not in parts:
        raise RuntimeError(f"Cannot parse default route line: {line}")
    idx = parts.index("dev")
    if idx + 1 >= len(parts):
        raise RuntimeError(f"Cannot parse WAN iface from: {line}")
    return parts[idx + 1]


def _iptables(*args: str, check: bool = True) -> None:
    _which("iptables")
    run_cmd(["iptables", *args], check=check)


def _iptables_capture(*args: str, check: bool = True) -> str:
    _which("iptables")
    return run_cmd(["iptables", *args], check=check).stdout


def _has_nat_table() -> bool:
    try:
        _iptables_capture("-t", "nat", "-S")
        return True
    except Exception:
        return False


def _list_chains(table: Optional[str]) -> List[str]:
    try:
        if table is None:
            out = _iptables_capture("-S")
        else:
            out = _iptables_capture("-t", table, "-S")
    except Exception:
        return []
    chains = []
    for line in out.splitlines():
        # chain definition lines: -N CHAIN
        if line.startswith("-N "):
            parts = line.split()
            if len(parts) >= 2:
                chains.append(parts[1])
    return chains


def _chain_exists(table: Optional[str], chain: str) -> bool:
    return chain in _list_chains(table)


def _ensure_chain(table: Optional[str], chain: str) -> None:
    if not _chain_exists(table, chain):
        if table is None:
            _iptables("-N", chain)
        else:
            _iptables("-t", table, "-N", chain)


def _flush_chain(table: Optional[str], chain: str) -> None:
    try:
        if table is None:
            _iptables("-F", chain)
        else:
            _iptables("-t", table, "-F", chain)
    except Exception:
        pass


def _ensure_jump_first(table: Optional[str], parent: str, jump_chain: str) -> None:
    """
    S'assure que parent commence par: -j <jump_chain>
    """
    try:
        if table is None:
            out = _iptables_capture("-S", parent)
        else:
            out = _iptables_capture("-t", table, "-S", parent)
    except Exception:
        out = ""

    needle = f"-A {parent} -j {jump_chain}"
    if needle in out:
        return

    if table is None:
        _iptables("-I", parent, "1", "-j", jump_chain)
    else:
        _iptables("-t", table, "-I", parent, "1", "-j", jump_chain)


def _delete_jump(table: Optional[str], parent: str, jump_chain: str) -> None:
    """
    Supprime toutes les occurrences du jump parent -> jump_chain par numéro.
    """
    try:
        if table is None:
            lines = _iptables_capture("-L", parent, "--line-numbers").splitlines()
        else:
            lines = _iptables_capture("-t", table, "-L", parent, "--line-numbers").splitlines()
    except Exception:
        return

    to_delete: List[int] = []
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        # header lines vary; ignore those that don't start with an int
        try:
            num = int(parts[0])
        except Exception:
            continue
        # crude but robust: line contains jump_chain token
        if f" {jump_chain}" in line:
            to_delete.append(num)

    for n in sorted(to_delete, reverse=True):
        try:
            if table is None:
                _iptables("-D", parent, str(n))
            else:
                _iptables("-t", table, "-D", parent, str(n))
        except Exception:
            pass


# -----------------------------
# Public API
# -----------------------------

def enable_firewall(
    wg_iface: str = "wg0",
    listen_port: int = 51820,
    wan_iface: Optional[str] = None,
) -> FirewallResult:
    if not _is_root():
        raise PermissionError("firewall enable requires root (run with sudo).")

    _which("iptables")
    _which("ip")

    if wan_iface is None:
        wan_iface = detect_wan_iface()

    res = FirewallResult(wan_iface=wan_iface, backend="iptables")

    # --- FILTER table (INPUT/FORWARD) ---
    _ensure_chain(None, CH_IN)
    _ensure_chain(None, CH_FWD)

    # idempotent: rebuild our chains each time
    _flush_chain(None, CH_IN)
    _flush_chain(None, CH_FWD)

    # INPUT: allow UDP WireGuard port
    _iptables("-A", CH_IN, "-p", "udp", "--dport", str(listen_port), "-j", "ACCEPT")
    res.input_udp = True

    # FORWARD: established/related (conntrack)
    try:
        _iptables("-A", CH_FWD, "-m", "conntrack", "--ctstate", "RELATED,ESTABLISHED", "-j", "ACCEPT")
        res.forward_established = True
    except Exception:
        res.forward_established = False
        res.notes += "conntrack unavailable; skipped ESTABLISHED,RELATED rule. "

    # FORWARD: wg -> WAN
    _iptables("-A", CH_FWD, "-i", wg_iface, "-o", wan_iface, "-j", "ACCEPT")
    res.forward_wg_to_wan = True

    _ensure_jump_first(None, "INPUT", CH_IN)
    _ensure_jump_first(None, "FORWARD", CH_FWD)

    # --- NAT table (optional) ---
    if _has_nat_table():
        _ensure_chain("nat", CH_NAT)
        _flush_chain("nat", CH_NAT)

        _iptables("-t", "nat", "-A", CH_NAT, "-o", wan_iface, "-j", "MASQUERADE")
        res.nat_masquerade = True

        _ensure_jump_first("nat", "POSTROUTING", CH_NAT)
    else:
        res.nat_masquerade = False
        res.notes += "nat table unavailable (missing iptable_nat/nf_nat); no internet for VPN clients. "

    return res


def disable_firewall(
    wg_iface: str = "wg0",
    listen_port: int = 51820,
    wan_iface: Optional[str] = None,
) -> None:
    if not _is_root():
        raise PermissionError("firewall disable requires root (run with sudo).")

    _which("iptables")

    # Remove jumps first
    _delete_jump(None, "INPUT", CH_IN)
    _delete_jump(None, "FORWARD", CH_FWD)

    # Remove chains (filter)
    for ch in (CH_IN, CH_FWD):
        try:
            _iptables("-F", ch)
            _iptables("-X", ch)
        except Exception:
            pass

    # NAT (if available)
    if _has_nat_table():
        _delete_jump("nat", "POSTROUTING", CH_NAT)
        try:
            _iptables("-t", "nat", "-F", CH_NAT)
            _iptables("-t", "nat", "-X", CH_NAT)
        except Exception:
            pass


def firewall_status() -> Dict[str, Any]:
    """
    Résumé "produit" + ruleset si besoin.

    Retour:
      {
        enabled: bool,
        backend: "iptables",
        nat_available: bool,
        wan_iface: Optional[str],
        ruleset: str
      }
    """
    _which("iptables")

    try:
        rules_filter = _iptables_capture("-S")
    except Exception:
        return {
            "enabled": False,
            "backend": "iptables",
            "nat_available": False,
            "wan_iface": None,
            "ruleset": "",
        }

    nat_available = _has_nat_table()
    rules_nat = ""
    if nat_available:
        try:
            rules_nat = _iptables_capture("-t", "nat", "-S")
        except Exception:
            nat_available = False
            rules_nat = "(nat table unavailable)\n"
    else:
        rules_nat = "(nat table unavailable)\n"

    # enabled heuristic: our chains exist AND at least one jump is present
    chains_filter = set(_list_chains(None))
    has_chains = (CH_IN in chains_filter) and (CH_FWD in chains_filter)

    has_jump_input = f"-A INPUT -j {CH_IN}" in rules_filter
    has_jump_fwd = f"-A FORWARD -j {CH_FWD}" in rules_filter

    has_jump_nat = False
    if nat_available:
        has_jump_nat = f"-A POSTROUTING -j {CH_NAT}" in rules_nat

    enabled = has_chains and (has_jump_input or has_jump_fwd or has_jump_nat)

    # best-effort WAN detect (safe even if not root)
    wan = None
    try:
        wan = detect_wan_iface()
    except Exception:
        wan = None

    return {
        "enabled": enabled,
        "backend": "iptables",
        "nat_available": nat_available,
        "wan_iface": wan,
        "ruleset": rules_filter + "\n" + rules_nat,
    }
