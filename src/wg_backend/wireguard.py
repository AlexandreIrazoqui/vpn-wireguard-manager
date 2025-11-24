# src/wg_backend/wireguard.py
from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Optional, List

from .models import GlobalState, Peer, ServerState
from .state import load_state, save_state
from .ipam import allocate_ip


# ---------- Génération de clés ----------

def _run(cmd: List[str]) -> str:
    out = subprocess.check_output(cmd, text=True).strip()
    return out


def generate_keypair() -> tuple[str, str]:
    """
    Retourne (private_key, public_key) en utilisant wg(8).
    Nécessite 'wg' installé sur la machine.
    """
    priv = _run(["wg", "genkey"])
    pub = _run(["wg", "pubkey"], input=None)  # on va lui passer priv via stdin plus bas


def generate_keypair() -> tuple[str, str]:
    priv = _run(["wg", "genkey"])
    # pubkey lit la clé privée sur stdin
    proc = subprocess.Popen(["wg", "pubkey"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    stdout, _ = proc.communicate(priv + "\n")
    pub = stdout.strip()
    return priv, pub


def generate_preshared_key() -> str:
    return _run(["wg", "genpsk"])


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

    if s.dns:
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

    if s.endpoint:
        lines.append(f"Endpoint = {s.endpoint}")

    # On force le keepalive si on veut du roaming téléphone
    lines.append("PersistentKeepalive = 25")

    return "\n".join(lines).strip() + "\n"


# ---------- Application système ----------

def write_server_conf_to_etc(state: GlobalState, path: Optional[Path] = None) -> Path:
    """
    Écrit /etc/wireguard/<interface>.conf
    """
    if path is None:
        Path("configs").mkdir(exist_ok=True)
        path = Path("configs") / f"{state.server.interface}.conf"
        path.parent.mkdir(parents=True, exist_ok=True)

    conf = render_server_conf(state)

    # Attention aux permissions : 600 recommandé
    with path.open("w", encoding="utf-8") as f:
        f.write(conf)
    path.chmod(0o600)
    return path


def wg_quick_reload(interface: str) -> None:
    raise RuntimeError(
        "wg_quick_reload() ne doit plus être appelé automatiquement. "
        "Utilise une commande dédiée 'vpn apply' ou applique manuellement."
    )
