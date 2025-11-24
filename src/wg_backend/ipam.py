# src/wg_backend/ipam.py
from __future__ import annotations
import ipaddress
from typing import Set
from .models import GlobalState


def get_used_ips(state: GlobalState) -> Set[ipaddress.IPv4Address]:
    net = ipaddress.ip_network(state.network_cidr)
    used = set()

    # IP du serveur
    server_ip_str = state.server.address.split("/")[0]
    used.add(ipaddress.ip_address(server_ip_str))

    # IP des peers
    for p in state.peers.values():
        ip_str = p.ip.split("/")[0]
        used.add(ipaddress.ip_address(ip_str))

    # On ignore network address + broadcast (par convention)
    used.add(net.network_address)
    used.add(net.broadcast_address)

    return used


def allocate_ip(state: GlobalState) -> str:
    """
    Retourne une nouvelle IP /32 libre sous forme '10.8.0.X/32'
    """
    net = ipaddress.ip_network(state.network_cidr)
    used = get_used_ips(state)

    for host in net.hosts():
        if host not in used:
            return f"{host}/32"

    raise RuntimeError("No free IP available in VPN network")
