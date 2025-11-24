
# src/wg_backend/models.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional, List


@dataclass
class Peer:
    name: str
    private_key: str
    public_key: str
    ip: str                # ex "10.8.0.2/32"
    allowed_ips: List[str] # en général ["10.8.0.0/24"]
    preshared_key: Optional[str] = None


@dataclass
class ServerState:
    interface: str             # ex: "wg0"
    listen_port: int           # ex: 51820
    private_key: str
    public_key: str
    address: str               # IP locale du serveur dans le VPN, ex "10.8.0.1/24"
    endpoint: Optional[str]    # IP publique:port pour les clients, ex "1.2.3.4:51820"
    dns: Optional[List[str]] = None  # DNS push pour les clients


@dataclass
class GlobalState:
    network_cidr: str                  # ex: "10.8.0.0/24"
    server: ServerState
    peers: Dict[str, Peer] = field(default_factory=dict)
