import argparse
from pathlib import Path
import qrcode
import sys

from wg_backend.init_server import init_server
from wg_backend.state import load_state, save_state

from wg_backend.wireguard import (
    add_peer,
    remove_peer,
    render_client_conf,
    write_server_conf,              # écrit dans ./configs (debug/export)
    status as wg_status,            # dict {interface, up, wg}
    wg_quick_up,
    wg_quick_down,
    apply_safe as wg_apply,              # installe /etc/wireguard + (optionnel) restart
    doctor as wg_doctor,
)


# ---------------------------------------------------
# Commande : init (initialisation du serveur)
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
# Commande : add-peer
# ---------------------------------------------------

def cmd_add_peer(args):
    state = load_state()

    peer = add_peer(state, args.name)
    save_state(state)

    # Met à jour la conf locale (utile debug/export)
    path = write_server_conf(state)
    print(f"[+] Fichier serveur généré (local) : {path}")

    print(f"[+] Peer ajouté : {peer.name}")
    print("[+] Configuration client :")
    print(render_client_conf(state, args.name))

    print("\n[!] Pour appliquer côté serveur :")
    print("    sudo vpn apply")


# ---------------------------------------------------
# Commande : list-peers
# ---------------------------------------------------

def cmd_list(args):
    state = load_state()

    print("=== Serveur ===")
    s = state.server
    print(f"Interface : {s.interface}")
    print(f"Adresse   : {s.address}")
    print(f"Port      : {s.listen_port}")
    print(f"Endpoint  : {s.endpoint}\n")

    print("=== Peers ===")
    if not state.peers:
        print("Aucun peer.")
    else:
        for name, p in state.peers.items():
            print(f"- {name} ({p.ip})")


# ---------------------------------------------------
# Commande : remove-peer
# ---------------------------------------------------

def cmd_remove_peer(args):
    state = load_state()

    try:
        remove_peer(state, args.name)
    except KeyError:
        print("[ERREUR] Peer introuvable.")
        return

    save_state(state)

    path = write_server_conf(state)
    print(f"[OK] Peer supprimé : {args.name}")
    print(f"[+] Fichier serveur généré (local) : {path}")

    print("\n[!] Pour appliquer côté serveur :")
    print("    sudo vpn apply")


# ---------------------------------------------------
# Commande : generate-qr
# ---------------------------------------------------

def cmd_generate_qr(args):
    state = load_state()

    try:
        conf = render_client_conf(state, args.name)
    except KeyError:
        print("Peer introuvable.")
        return

    img = qrcode.make(conf)
    path = f"configs/{args.name}.png"

    Path("configs").mkdir(exist_ok=True)
    img.save(path)

    print(f"[OK] QR code généré : {path}")


# ---------------------------------------------------
# Commande : export-peer
# ---------------------------------------------------

def cmd_export_peer(args):
    state = load_state()

    try:
        conf = render_client_conf(state, args.name)
    except KeyError:
        print("[ERREUR] Peer introuvable.")
        return

    Path("configs").mkdir(exist_ok=True)
    path = Path(f"configs/{args.name}.conf")
    path.write_text(conf, encoding="utf-8")

    print(f"[OK] Config générée : {path}")
    print("\n--- Configuration ---\n")
    print(conf)


# ---------------------------------------------------
# Commande : apply (installe /etc/wireguard + restart)
# ---------------------------------------------------

def cmd_apply(args):
    state = load_state()
    # restart par défaut; --no-restart pour juste installer
    path = wg_apply(state, restart=not args.no_restart)
    print(f"[OK] Configuration installée : {path}")
    if args.no_restart:
        print("[!] --no-restart : l'interface n'a pas été redémarrée.")


# ---------------------------------------------------
# Commande : show-peer
# ---------------------------------------------------

def cmd_show_peer(args):
    state = load_state()
    p = state.peers.get(args.name)
    if p is None:
        print("[ERREUR] Peer introuvable.")
        return

    s = state.server
    print(f"Peer: {p.name}")
    print(f"- IP: {p.ip}")
    print(f"- Public key: {p.public_key}")
    print(f"- Allowed IPs: {', '.join(p.allowed_ips)}")
    if s.endpoint:
        print(f"- Endpoint: {s.endpoint}")
    if s.dns:
        print(f"- DNS: {', '.join(s.dns)}")
    print("- PersistentKeepalive: 25")

    if args.secrets:
        print(f"- Private key: {p.private_key}")
        if p.preshared_key:
            print(f"- Preshared key: {p.preshared_key}")


# ---------------------------------------------------
# Commande : export-all
# ---------------------------------------------------

def cmd_export_all(args):
    state = load_state()
    Path("configs").mkdir(exist_ok=True)

    count = 0
    for name in state.peers.keys():
        conf = render_client_conf(state, name)
        path = Path("configs") / f"{name}.conf"
        path.write_text(conf, encoding="utf-8")
        count += 1

    print(f"[OK] export-all : {count} configs générées dans configs/")


# ---------------------------------------------------
# Commandes : enable / disable / status
# ---------------------------------------------------

def _resolve_iface(args) -> str:
    if getattr(args, "iface", None):
        return args.iface
    state = load_state()
    return state.server.interface


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
        print(f"[DOWN] Interface '{iface}' is down")
        return

    print(f"[UP] Interface '{iface}' is up")
    if res["wg"]:
        print(res["wg"])


def cmd_doctor(args):
    try:
        state = load_state()
    except Exception:
        # state.json absent ou illisible : doctor doit quand même tourner
        state = None

    checks = wg_doctor(state)

    ok_count = 0
    for c in checks:
        mark = "OK" if c.ok else "KO"
        print(f"[{mark}] {c.name}: {c.details}")
        if not c.ok and c.fix:
            print(f"      fix: {c.fix}")
        if c.ok:
            ok_count += 1

    total = len(checks)
    print(f"\nResult: {ok_count}/{total} checks OK")
    if ok_count == total:
        print("=> Ready (base) for server testing.")
    else:
        print("=> Fix KO items before thinclient deployment.")
# ---------------------------------------------------
# CLI / Parser
# ---------------------------------------------------

def main():
    parser = argparse.ArgumentParser(prog="vpn")
    sub = parser.add_subparsers(dest="cmd")

    # init
    p_init = sub.add_parser("init")
    p_init.add_argument("--endpoint", required=False)
    p_init.add_argument("--port", type=int, default=51820)
    p_init.add_argument("--iface", required=False, help="Interface (default wg0)")
    p_init.set_defaults(func=cmd_init)

    # add-peer
    p_add = sub.add_parser("add-peer")
    p_add.add_argument("name")
    p_add.set_defaults(func=cmd_add_peer)

    # list-peers
    p_list = sub.add_parser("list-peers")
    p_list.set_defaults(func=cmd_list)

    # remove-peer
    p_rm = sub.add_parser("remove-peer")
    p_rm.add_argument("name")
    p_rm.set_defaults(func=cmd_remove_peer)

    # export-peer
    p_export = sub.add_parser("export-peer")
    p_export.add_argument("name")
    p_export.set_defaults(func=cmd_export_peer)

    # generate-qr
    p_qr = sub.add_parser("generate-qr")
    p_qr.add_argument("name")
    p_qr.set_defaults(func=cmd_generate_qr)

    # apply
    p_apply = sub.add_parser("apply")
    p_apply.add_argument(
        "--no-restart",
        action="store_true",
        help="Installe la conf dans /etc/wireguard mais ne redémarre pas l'interface",
    )
    p_apply.set_defaults(func=cmd_apply)

    # enable / disable / status
    p_enable = sub.add_parser("enable", help="wg-quick up <iface>")
    p_enable.add_argument("--iface", help="Interface name (default: from state)")
    p_enable.set_defaults(func=cmd_enable)

    p_disable = sub.add_parser("disable", help="wg-quick down <iface>")
    p_disable.add_argument("--iface", help="Interface name (default: from state)")
    p_disable.set_defaults(func=cmd_disable)

    p_status = sub.add_parser("status", help="Show interface status + wg show")
    p_status.add_argument("--iface", help="Interface name (default: from state)")
    p_status.set_defaults(func=cmd_status)

    # show-peer
    p_show = sub.add_parser("show-peer", help="Affiche les infos d'un peer")
    p_show.add_argument("name")
    p_show.add_argument("--secrets", action="store_true", help="Affiche aussi les clés privées/psk")
    p_show.set_defaults(func=cmd_show_peer)

    # export-all
    p_export_all = sub.add_parser("export-all")
    p_export_all.set_defaults(func=cmd_export_all)

    # doctor
    p_doctor = sub.add_parser("doctor", help="Checks machine readiness for WireGuard server")
    p_doctor.set_defaults(func=cmd_doctor)
    # parse
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return

    try:
        args.func(args)
    except Exception as e:
        print(f"[ERREUR] {e}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
