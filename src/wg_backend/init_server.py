# src/wg_backend/init_server.py

from __future__ import annotations
from pathlib import Path
from .models import GlobalState, ServerState
from .state import save_state
from .wireguard import generate_keypair

def init_server(
    interface: str = "wg0",
    network_cidr: str = "10.8.0.0/24",
    listen_port: int = 51820,
    endpoint: str | None = None,
    dns: list[str] | None = None,
    state_path: Path | None = None,
):
    private_key, public_key = generate_keypair()

    server = ServerState(
        interface=interface,
        listen_port=listen_port,
        private_key=private_key,
        public_key=public_key,
        address="10.8.0.1/24",  # Première IP du réseau
        endpoint=endpoint,
        dns=dns,
    )

    state = GlobalState(
        network_cidr=network_cidr,
        server=server,
        peers={},  # vide pour l'instant
    )

    save_state(state, state_path)
    return state
