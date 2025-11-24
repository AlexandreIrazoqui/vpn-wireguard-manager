# src/wg_backend/state.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
from .models import GlobalState, ServerState, Peer


DEFAULT_STATE_PATH = Path("data/state.json")


def state_to_dict(state: GlobalState) -> dict:
    return {
        "network_cidr": state.network_cidr,
        "server": {
            "interface": state.server.interface,
            "listen_port": state.server.listen_port,
            "private_key": state.server.private_key,
            "public_key": state.server.public_key,
            "address": state.server.address,
            "endpoint": state.server.endpoint,
            "dns": state.server.dns,
        },
        "peers": {
            name: {
                "name": p.name,
                "private_key": p.private_key,
                "public_key": p.public_key,
                "ip": p.ip,
                "allowed_ips": p.allowed_ips,
                "preshared_key": p.preshared_key,
            }
            for name, p in state.peers.items()
        },
    }


def dict_to_state(data: dict) -> GlobalState:
    server_data = data["server"]
    server = ServerState(
        interface=server_data["interface"],
        listen_port=server_data["listen_port"],
        private_key=server_data["private_key"],
        public_key=server_data["public_key"],
        address=server_data["address"],
        endpoint=server_data.get("endpoint"),
        dns=server_data.get("dns"),
    )

    peers = {}
    for name, p in data.get("peers", {}).items():
        peers[name] = Peer(
            name=p["name"],
            private_key=p["private_key"],
            public_key=p["public_key"],
            ip=p["ip"],
            allowed_ips=p["allowed_ips"],
            preshared_key=p.get("preshared_key"),
        )

    return GlobalState(
        network_cidr=data["network_cidr"],
        server=server,
        peers=peers,
    )


def load_state(path: Optional[Path] = None) -> GlobalState:
    path = path or DEFAULT_STATE_PATH
    if not path.exists():
        raise FileNotFoundError(f"State file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return dict_to_state(data)


def save_state(state: GlobalState, path: Optional[Path] = None) -> None:
    path = path or DEFAULT_STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = state_to_dict(state)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
