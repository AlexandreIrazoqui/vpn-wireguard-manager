# src/wg_backend/wireguard.py
from __future__ import annotations

import os
import shutil
import subprocess
import ipaddress
import datetime

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

from .models import GlobalState, Peer
from .ipam import allocate_ip


# ---------- Utils commandes système ----------

@dataclass
class CmdResult:
    cmd: List[str]
    returncode: int
    stdout: str
    stderr: str


class CommandError(RuntimeError):
    def __init__(self, res: CmdResult):
        msg = (
            f"Command failed ({res.returncode}): {' '.join(res.cmd)}\n"
            f"{res.stderr.strip()}"
        )
        super().__init__(msg)
        self.res = res


def _which(prog: str) -> str:
    p = shutil.which(prog)
    if not p:
        raise FileNotFoundError(f"Required binary not found in PATH: {prog}")
    return p


def _is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def run_cmd(cmd: List[str], check: bool = True) -> CmdResult:
    # Vérif binaire dispo pour un message d'erreur clair
    _which(cmd[0])

    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
    )
    res = CmdResult(
        cmd=cmd,
        returncode=proc.returncode,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
    )
    if check and res.returncode != 0:
        raise CommandError(res)
    return res


def _run_check_output(cmd: List[str]) -> str:
    """Compat: petit helper pour les commandes qui retournent juste stdout."""
    return run_cmd(cmd, check=True).stdout.strip()


# ---------- Génération de clés ----------

def generate_keypair() -> tuple[str, str]:
    priv = _run_check_output(["wg", "genkey"])
    # pubkey lit la clé privée sur stdin
    _which("wg")
    proc = subprocess.Popen(
        ["wg", "pubkey"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = proc.communicate(priv + "\n")
    if proc.returncode != 0:
        raise RuntimeError(f"wg pubkey failed: {stderr.strip()}")
    pub = (stdout or "").strip()
    return priv, pub


def generate_preshared_key() -> str:
    return _run_check_output(["wg", "genpsk"])


# ---------- Gestion des peers ----------

def add_peer(
    state: GlobalState,
    name: str,
    with_preshared: bool = True,
) -> Peer:
    if name in state.peers:
        raise ValueError(f"Peer '{name}' already exists")

    ip = allocate_ip(state)
    priv, pub = generate_keypair()
    psk = generate_preshared_key() if with_preshared else None

    peer = Peer(
        name=name,
        private_key=priv,
        public_key=pub,
        ip=ip,
        allowed_ips=[state.network_cidr],  # full VPN network
        preshared_key=psk,
    )

    state.peers[name] = peer
    return peer


def remove_peer(state: GlobalState, name: str) -> None:
    if name not in state.peers:
        raise KeyError(f"Peer '{name}' does not exist")
    del state.peers[name]


# ---------- Rendu des configs ----------

def render_server_conf(state: GlobalState) -> str:
    s = state.server

    lines = [
        "[Interface]",
        f"Address = {s.address}",
        f"ListenPort = {s.listen_port}",
        f"PrivateKey = {s.private_key}",
        "",  # blank line
    ]

    for p in state.peers.values():
        lines.append("[Peer]")
        lines.append(f"PublicKey = {p.public_key}")
        if p.preshared_key:
            lines.append(f"PresharedKey = {p.preshared_key}")
        # côté serveur: AllowedIPs = l'IP du peer (souvent /32)
        lines.append(f"AllowedIPs = {p.ip}")
        lines.append("")  # blank

    return "\n".join(lines).strip() + "\n"


def render_client_conf(state: GlobalState, peer_name: str) -> str:
    if peer_name not in state.peers:
        raise KeyError(f"Unknown peer '{peer_name}'")

    p = state.peers[peer_name]
    s = state.server

    lines = [
        "[Interface]",
        f"Address = {p.ip}",
        f"PrivateKey = {p.private_key}",
    ]

    if getattr(s, "dns", None):
        lines.append(f"DNS = {', '.join(s.dns)}")

    lines += [
        "",
        "[Peer]",
        f"PublicKey = {s.public_key}",
    ]

    if p.preshared_key:
        lines.append(f"PresharedKey = {p.preshared_key}")

    lines += [
        f"AllowedIPs = {', '.join(p.allowed_ips)}",
    ]

    if getattr(s, "endpoint", None):
        lines.append(f"Endpoint = {s.endpoint}")

    # keepalive utile pour clients derrière NAT (téléphone)
    lines.append("PersistentKeepalive = 25")

    return "\n".join(lines).strip() + "\n"


# ---------- I/O fichiers ----------

def write_server_conf(
    state: GlobalState,
    path: Optional[Path] = None,
) -> Path:
    """
    Écrit la conf serveur à l'endroit demandé (par défaut ./configs/<iface>.conf).
    Pratique pour debug/exports sans toucher au système.
    """
    if path is None:
        path = Path("configs") / f"{state.server.interface}.conf"
    path.parent.mkdir(parents=True, exist_ok=True)

    conf = render_server_conf(state)
    path.write_text(conf, encoding="utf-8")
    path.chmod(0o600)
    return path


def install_server_conf_to_etc(state: GlobalState) -> Path:
    """
    Installe /etc/wireguard/<interface>.conf (root requis)
    """
    if not _is_root():
        raise PermissionError("Writing to /etc/wireguard requires root (run with sudo).")

    etc_dir = Path("/etc/wireguard")
    etc_dir.mkdir(parents=True, exist_ok=True)

    target = etc_dir / f"{state.server.interface}.conf"
    conf = render_server_conf(state)

    # écriture atomique
    tmp = target.with_suffix(".conf.tmp")
    tmp.write_text(conf, encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(target)

    return target


# ---------- Actions système WireGuard ----------

def link_is_up(interface: str) -> bool:
    # ip link show dev wg0 => returncode 0 si existe
    res = run_cmd(["ip", "link", "show", "dev", interface], check=False)
    return res.returncode == 0


def wg_show(interface: Optional[str] = None) -> str:
    cmd = ["wg", "show"]
    if interface:
        cmd.append(interface)
    return run_cmd(cmd, check=True).stdout.strip()


def wg_quick_up(interface: str) -> None:
    if not _is_root():
        raise PermissionError("wg-quick up requires root (run with sudo).")
    run_cmd(["wg-quick", "up", interface], check=True)


def wg_quick_down(interface: str) -> None:
    if not _is_root():
        raise PermissionError("wg-quick down requires root (run with sudo).")
    run_cmd(["wg-quick", "down", interface], check=True)


def status(interface: str) -> dict:
    up = link_is_up(interface)
    info = wg_show(interface) if up else ""
    return {"interface": interface, "up": up, "wg": info}


# ---------- Validation (apply safe) ----------

def validate_state(state: GlobalState) -> list[str]:
    """
    Retourne une liste d'erreurs (strings). Si vide => OK.
    Validation volontairement simple mais bloquante pour éviter de casser le serveur.
    """
    errors: list[str] = []

    s = state.server

    # Champs serveur minimaux
    if not getattr(s, "interface", None) or not str(s.interface).strip():
        errors.append("server.interface manquant/vide")
    if not getattr(s, "private_key", None) or not str(s.private_key).strip():
        errors.append("server.private_key manquante/vide")
    if not getattr(s, "address", None) or not str(s.address).strip():
        errors.append("server.address manquante/vide")
    if not isinstance(getattr(s, "listen_port", None), int) or not (1 <= s.listen_port <= 65535):
        errors.append("server.listen_port invalide (doit être int 1..65535)")

    # Parse réseau
    try:
        net = ipaddress.ip_network(state.network_cidr, strict=False)
    except Exception:
        errors.append(f"network_cidr invalide: {state.network_cidr}")
        net = None  # type: ignore

    # Parse address serveur (ex: "10.8.0.1/24")
    try:
        ipaddress.ip_interface(s.address)
    except Exception:
        errors.append(f"server.address invalide: {s.address}")

    # Validation peers
    seen_ips: set[str] = set()
    for name, p in state.peers.items():
        # Nom peer : basique, évite surprises filesystem/cli
        if not isinstance(name, str) or not name:
            errors.append("peer avec nom vide")
        if any(ch in name for ch in ("/", "\\", "..")):
            errors.append(f"peer name interdit: {name!r} (chemins interdits)")

        # IP peer
        try:
            peer_iface = ipaddress.ip_interface(p.ip)
        except Exception:
            errors.append(f"peer {name}: ip invalide: {p.ip}")
            continue

        ip_str = str(peer_iface)
        if ip_str in seen_ips:
            errors.append(f"peer {name}: IP en doublon: {p.ip}")
        seen_ips.add(ip_str)

        if net is not None:
            if peer_iface.ip not in net:
                errors.append(f"peer {name}: IP hors network_cidr ({p.ip} ∉ {state.network_cidr})")

        # Clés minimales
        if not getattr(p, "public_key", None) or not str(p.public_key).strip():
            errors.append(f"peer {name}: public_key manquante/vide")
        if not getattr(p, "private_key", None) or not str(p.private_key).strip():
            errors.append(f"peer {name}: private_key manquante/vide")

        # AllowedIPs côté client : doit être non vide
        if not getattr(p, "allowed_ips", None) or len(p.allowed_ips) == 0:
            errors.append(f"peer {name}: allowed_ips vide")

    return errors


def backup_etc_conf(interface: str) -> Optional[Path]:
    """
    Sauvegarde /etc/wireguard/<iface>.conf -> /etc/wireguard/<iface>.conf.bak-YYYYmmdd-HHMMSS
    Retourne le path de backup si backup fait, sinon None.
    """
    src = Path("/etc/wireguard") / f"{interface}.conf"
    if not src.exists():
        return None

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = src.with_name(f"{interface}.conf.bak-{ts}")
    # copie simple (texte), garde perms en rechmod ensuite si besoin
    dst.write_bytes(src.read_bytes())
    try:
        dst.chmod(0o600)
    except Exception:
        pass
    return dst


def apply_safe(state: GlobalState, restart: bool = True) -> Path:
    """
    SAFE apply:
    - valide l'état
    - root required
    - backup de l'ancienne conf /etc/wireguard/<iface>.conf
    - installe la nouvelle conf atomiquement
    - (optionnel) restart wg-quick down/up
    """
    errs = validate_state(state)
    if errs:
        msg = "State invalide, apply refusé:\n- " + "\n- ".join(errs)
        raise ValueError(msg)

    iface = state.server.interface

    if not _is_root():
        raise PermissionError("apply requires root (run with sudo).")

    # Vérif binaires avant de toucher à /etc
    _which("wg")
    _which("wg-quick")
    _which("ip")

    Path("/etc/wireguard").mkdir(parents=True, exist_ok=True)

    bak = backup_etc_conf(iface)
    if bak:
        # pas de print ici (backend), la CLI affichera éventuellement
        pass

    path = install_server_conf_to_etc(state)

    if restart:
        if link_is_up(iface):
            wg_quick_down(iface)
        wg_quick_up(iface)

    return path

# ---------- Diagnostics (vpn doctor) ----------

from dataclasses import dataclass
import re

@dataclass
class DoctorCheck:
    name: str
    ok: bool
    details: str
    fix: str = ""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _check_binary(prog: str) -> DoctorCheck:
    try:
        p = _which(prog)
        return DoctorCheck(
            name=f"binary:{prog}",
            ok=True,
            details=f"found: {p}",
        )
    except Exception as e:
        return DoctorCheck(
            name=f"binary:{prog}",
            ok=False,
            details=str(e),
            fix=f"Install it (Arch: pacman -S { 'wireguard-tools' if prog in ('wg','wg-quick') else prog })",
        )


def _check_state_file(state_path: Path = Path("data/state.json")) -> DoctorCheck:
    if state_path.exists():
        return DoctorCheck(
            name="state:file",
            ok=True,
            details=f"found: {state_path}",
        )
    return DoctorCheck(
        name="state:file",
        ok=False,
        details=f"missing: {state_path}",
        fix="Run: vpn init (to create data/state.json)",
    )


def _check_ip_forward() -> DoctorCheck:
    p = Path("/proc/sys/net/ipv4/ip_forward")
    val = _read_text(p)
    if val == "1":
        return DoctorCheck(
            name="sysctl:ip_forward",
            ok=True,
            details="net.ipv4.ip_forward = 1",
        )
    if val == "0":
        return DoctorCheck(
            name="sysctl:ip_forward",
            ok=False,
            details="net.ipv4.ip_forward = 0",
            fix="Enable routing: sysctl -w net.ipv4.ip_forward=1 (and persist in /etc/sysctl.d/*.conf)",
        )
    return DoctorCheck(
        name="sysctl:ip_forward",
        ok=False,
        details="cannot read /proc/sys/net/ipv4/ip_forward",
        fix="Check permissions / kernel procfs",
    )


def _check_etc_wireguard_dir() -> DoctorCheck:
    d = Path("/etc/wireguard")
    if d.exists() and d.is_dir():
        return DoctorCheck(
            name="fs:/etc/wireguard",
            ok=True,
            details="exists",
        )
    return DoctorCheck(
        name="fs:/etc/wireguard",
        ok=False,
        details="missing",
        fix="Create it (as root): mkdir -p /etc/wireguard",
    )


def _check_installed_conf(interface: str) -> DoctorCheck:
    p = Path("/etc/wireguard") / f"{interface}.conf"
    if not p.exists():
        return DoctorCheck(
            name="fs:server_conf",
            ok=False,
            details=f"missing: {p}",
            fix="Run: sudo vpn apply (installs /etc/wireguard/<iface>.conf)",
        )

    # existe : essaye de stat (peut échouer si perms)
    try:
        mode = oct(p.stat().st_mode & 0o777)
        return DoctorCheck(
            name="fs:server_conf",
            ok=True,
            details=f"found: {p} (mode {mode})",
            fix="",
        )
    except PermissionError:
        return DoctorCheck(
            name="fs:server_conf",
            ok=True,
            details=f"found: {p} (permission denied to stat/read without sudo — ok)",
            fix="Run doctor with sudo if you want full checks: sudo vpn doctor",
        )

def _check_conf_sanity(conf_text: str) -> DoctorCheck:
    # Check minimal structure
    ok = True
    problems = []

    if "[Interface]" not in conf_text:
        ok = False
        problems.append("missing [Interface]")
    if not re.search(r"(?m)^\s*PrivateKey\s*=", conf_text):
        ok = False
        problems.append("missing PrivateKey")
    if not re.search(r"(?m)^\s*Address\s*=", conf_text):
        ok = False
        problems.append("missing Address")

    if ok:
        return DoctorCheck(
            name="conf:sanity",
            ok=True,
            details="server conf looks minimally valid",
        )
    return DoctorCheck(
        name="conf:sanity",
        ok=False,
        details="; ".join(problems),
        fix="Fix server state fields and regenerate conf (vpn init / add-peer / apply).",
    )


def _check_interface_state(interface: str) -> DoctorCheck:
    up = link_is_up(interface)
    if up:
        return DoctorCheck(
            name="wg:interface",
            ok=True,
            details=f"{interface} exists (UP-ish). 'wg show {interface}' should work.",
        )
    return DoctorCheck(
        name="wg:interface",
        ok=False,
        details=f"{interface} not present (down)",
        fix=f"Bring it up: sudo vpn enable --iface {interface} (or sudo wg-quick up {interface})",
    )


def doctor(state: Optional["GlobalState"] = None) -> list[DoctorCheck]:
    """
    Run a set of checks to see if the machine is ready to run WireGuard server.
    If state is provided, uses it. Otherwise tries to load from default path via caller.
    """
    checks: list[DoctorCheck] = []

    # Binaries
    checks.append(_check_binary("wg"))
    checks.append(_check_binary("wg-quick"))
    checks.append(_check_binary("ip"))

    # State file presence (doesn't require parsing)
    checks.append(_check_state_file(Path("data/state.json")))

    # /etc/wireguard
    checks.append(_check_etc_wireguard_dir())

    # If state provided, do deeper checks
    if state is not None:
        iface = state.server.interface

        # Conf generation sanity (no root needed)
        conf_text = render_server_conf(state)
        checks.append(_check_conf_sanity(conf_text))

        # Installed conf
        checks.append(_check_installed_conf(iface))

        # Interface state (non-root)
        checks.append(_check_interface_state(iface))

    # Routing (for “full VPN” usage)
    checks.append(_check_ip_forward())

    # Root note (not a pass/fail, but helpful)
    checks.append(
        DoctorCheck(
            name="hint:root",
            ok=_is_root(),
            details="running as root" if _is_root() else "not root (ok for status/doctor, required for apply/enable/disable)",
            fix="Use sudo for commands that touch /etc/wireguard or wg-quick.",
        )
    )

    return checks
# ---------- Compat / garde-fou ----------

def wg_quick_reload(interface: str) -> None:
    raise RuntimeError(
        "wg_quick_reload() ne doit plus être appelé automatiquement. "
        "Utilise une commande dédiée 'vpn apply' ou 'vpn enable/disable'."
    )
