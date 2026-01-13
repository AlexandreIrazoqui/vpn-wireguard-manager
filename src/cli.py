import argparse
from pathlib import Path
import qrcode
import sys

from wg_backend.init_server import init_server
from wg_backend.state import load_state, save_state
from wg_backend.firewall import enable_firewall, disable_firewall, firewall_status

from wg_backend.wireguard import (
    add_peer,
    remove_peer,
    render_client_conf,
    write_server_conf,
    status as wg_status,
    wg_quick_up,
    wg_quick_down,
    apply_safe as wg_apply,
    doctor as wg_doctor,
)


# ---------------------------------------------------
# Helpers
# ---------------------------------------------------

def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _resolve_iface(args) -> str:
    if getattr(args, "iface", None):
        return args.iface
    state = load_state()
    return state.server.interface


# ---------------------------------------------------
# Commande : init
# ---------------------------------------------------

def cmd_init(args):
    print("[*] Initialisation du serveur WireGuard...")

    state = init_server(
        interface=args.iface or "wg0",
        network_cidr="10.8.0.0/24",
        listen_port=args.port,
        endpoint=args.endpoint,
        dns=["1.1.1.1", "8.8.8.8"],
        state_path=Path("data/state.json"),
    )

    print("[+] Serveur initialisé.")
    print("[+] Adresse :", state.server.address)
    print("[+] Fichier data/state.json créé.")


# ---------------------------------------------------
# Peers
# ---------------------------------------------------

def cmd_add_peer(args):
    state = load_state()
    peer = add_peer(state, args.name)
    save_state(state)

    path = write_server_conf(state)
    print(f"[+] Peer ajouté : {peer.name}")
    print(f"[+] Fichier serveur généré (local) : {path}")
    print(render_client_conf(state, args.name))
    print("\n[!] sudo vpn apply")


def cmd_list(args):
    state = load_state()
    s = state.server

    print("=== Serveur ===")
    print(f"Interface : {s.interface}")
    print(f"Adresse   : {s.address}")
    print(f"Port      : {s.listen_port}")
    print(f"Endpoint  : {s.endpoint}\n")

    print("=== Peers ===")
    if not state.peers:
        print("Aucun peer.")
        return
    for name, p in state.peers.items():
        print(f"- {name} ({p.ip})")


def cmd_remove_peer(args):
    state = load_state()
    remove_peer(state, args.name)
    save_state(state)

    path = write_server_conf(state)
    print(f"[OK] Peer supprimé : {args.name}")
    print(f"[+] Fichier serveur généré (local) : {path}")
    print("\n[!] sudo vpn apply")


def cmd_generate_qr(args):
    state = load_state()
    conf = render_client_conf(state, args.name)

    img = qrcode.make(conf)
    Path("configs").mkdir(exist_ok=True)
    path = f"configs/{args.name}.png"
    img.save(path)

    print(f"[OK] QR code généré : {path}")


def cmd_export_peer(args):
    state = load_state()
    conf = render_client_conf(state, args.name)

    Path("configs").mkdir(exist_ok=True)
    path = Path(f"configs/{args.name}.conf")
    path.write_text(conf, encoding="utf-8")

    print(f"[OK] Config générée : {path}")
    print(conf)


def cmd_export_all(args):
    state = load_state()
    Path("configs").mkdir(exist_ok=True)

    for name in state.peers:
        conf = render_client_conf(state, name)
        Path(f"configs/{name}.conf").write_text(conf, encoding="utf-8")

    print(f"[OK] export-all : {len(state.peers)} configs générées")


# ---------------------------------------------------
# WireGuard lifecycle
# ---------------------------------------------------

def cmd_apply(args):
    state = load_state()
    path = wg_apply(state, restart=not args.no_restart)
    print(f"[OK] Configuration installée : {path}")


def cmd_enable(args):
    iface = _resolve_iface(args)
    wg_quick_up(iface)
    print(f"[OK] Interface '{iface}' enabled")


def cmd_disable(args):
    iface = _resolve_iface(args)
    wg_quick_down(iface)
    print(f"[OK] Interface '{iface}' disabled")


def cmd_status(args):
    iface = _resolve_iface(args)
    res = wg_status(iface)

    if not res["up"]:
        print(f"[DOWN] Interface '{iface}'")
        return

    print(f"[UP] Interface '{iface}'")
    if res["wg"]:
        print(res["wg"])


# ---------------------------------------------------
# Doctor
# ---------------------------------------------------

def cmd_doctor(args):
    try:
        state = load_state()
    except Exception:
        state = None

    checks = wg_doctor(state)
    ok = 0

    for c in checks:
        mark = "OK" if c.ok else "KO"
        print(f"[{mark}] {c.name}: {c.details}")
        if not c.ok and c.fix:
            print(f"      fix: {c.fix}")
        if c.ok:
            ok += 1

    print(f"\nResult: {ok}/{len(checks)} checks OK")


# ---------------------------------------------------
# Firewall (iptables)
# ---------------------------------------------------

def cmd_fw_enable(args):
    state = load_state()
    iface = state.server.interface
    port = state.server.listen_port

    res = enable_firewall(
        wg_iface=iface,
        listen_port=port,
        wan_iface=args.wan,
    )

    print(f"[OK] firewall enabled (WG={iface}, port={port}/udp, WAN={_get(res,'wan_iface','auto')})")

    flags = []
    for k in ("input_udp", "forward_established", "forward_wg_to_wan", "nat_masquerade"):
        v = _get(res, k)
        if v is not None:
            flags.append(f"{k}={v}")
    if flags:
        print("     " + ", ".join(flags))

    notes = _get(res, "notes")
    if notes:
        print(f"[WARN] {notes}")


def cmd_fw_disable(args):
    state = load_state()
    iface = state.server.interface
    port = state.server.listen_port

    disable_firewall(
        wg_iface=iface,
        listen_port=port,
        wan_iface=args.wan,
    )

    print(f"[OK] firewall disabled (WG={iface}, WAN={args.wan or 'auto'})")


def cmd_fw_status(args):
    st = firewall_status()
    if not _get(st, "enabled", False):
        print("[DOWN] firewall not enabled")
        return

    print("[UP] firewall enabled")
    print(f"     NAT available: {_get(st,'nat_available',False)}")
    if _get(st, "wan_iface"):
        print(f"     WAN iface: {_get(st,'wan_iface')}")

    if args.verbose and _get(st, "ruleset"):
        print(st["ruleset"])


# ---------------------------------------------------
# CLI
# ---------------------------------------------------

def main():
    parser = argparse.ArgumentParser(prog="vpn")
    sub = parser.add_subparsers(dest="cmd")

    p_init = sub.add_parser("init")
    p_init.add_argument("--endpoint")
    p_init.add_argument("--port", type=int, default=51820)
    p_init.add_argument("--iface")
    p_init.set_defaults(func=cmd_init)

    sub.add_parser("list-peers").set_defaults(func=cmd_list)

    p = sub.add_parser("add-peer")
    p.add_argument("name")
    p.set_defaults(func=cmd_add_peer)

    p = sub.add_parser("remove-peer")
    p.add_argument("name")
    p.set_defaults(func=cmd_remove_peer)

    p = sub.add_parser("export-peer")
    p.add_argument("name")
    p.set_defaults(func=cmd_export_peer)

    p = sub.add_parser("export-all")
    p.set_defaults(func=cmd_export_all)

    p = sub.add_parser("generate-qr")
    p.add_argument("name")
    p.set_defaults(func=cmd_generate_qr)

    p = sub.add_parser("apply")
    p.add_argument("--no-restart", action="store_true")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("enable")
    p.add_argument("--iface")
    p.set_defaults(func=cmd_enable)

    p = sub.add_parser("disable")
    p.add_argument("--iface")
    p.set_defaults(func=cmd_disable)

    p = sub.add_parser("status")
    p.add_argument("--iface")
    p.set_defaults(func=cmd_status)

    sub.add_parser("doctor").set_defaults(func=cmd_doctor)

    p_fw = sub.add_parser("firewall", help="Firewall/NAT management (iptables)")
    fw = p_fw.add_subparsers(dest="fw_cmd", required=True)

    p = fw.add_parser("enable")
    p.add_argument("--wan")
    p.set_defaults(func=cmd_fw_enable)

    p = fw.add_parser("disable")
    p.add_argument("--wan")
    p.set_defaults(func=cmd_fw_disable)

    p = fw.add_parser("status")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_fw_status)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return

    try:
        args.func(args)
    except Exception as e:
        print(f"[ERREUR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
