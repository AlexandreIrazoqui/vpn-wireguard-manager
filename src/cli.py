import argparse
from pathlib import Path
import qrcode

from wg_backend.wireguard import render_client_conf
from wg_backend.init_server import init_server
from wg_backend.state import load_state, save_state
from wg_backend.wireguard import (
    add_peer,
    remove_peer,
    render_client_conf,
    write_server_conf_to_etc,
    wg_quick_reload,
)


# ---------------------------------------------------
# Commande : init (initialisation du serveur)
# ---------------------------------------------------

def cmd_init(args):
    print("[*] Initialisation du serveur WireGuard...")

    state = init_server(
        interface="wg0",
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

    # Regénère wg0.conf et reload
    path = write_server_conf_to_etc(state)
    print(f"[+] Fichier serveur mis à jour : {path}")
    print("[!] Pense à appliquer la config avec :")
    print(f"    sudo cp {path} /etc/wireguard/wg0.conf && sudo wg-quick down wg0 && sudo wg-quick up wg0")

    print(f"[+] Peer ajouté : {peer.name}")
    print("[+] Configuration client :")
    print(render_client_conf(state, args.name))


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

    # Mise à jour du fichier wg0.conf local
    path = write_server_conf_to_etc(state)
    print(f"[OK] Peer supprimé : {args.name}")
    print(f"[+] Fichier serveur mis à jour : {path}")
    print("[!] Pense à appliquer la config avec :")
    print(f"    sudo cp {path} /etc/wireguard/wg0.conf && sudo wg-quick down wg0 && sudo wg-quick up wg0")
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

def cmd_export_peer(args):
    state = load_state()

    try:
        conf = render_client_conf(state, args.name)
    except KeyError:
        print("[ERREUR] Peer introuvable.")
        return

    Path("configs").mkdir(exist_ok=True)
    path = Path(f"configs/{args.name}.conf")
    path.write_text(conf)

    print(f"[OK] Config générée : {path}")
    print("\n--- Configuration ---\n")
    print(conf)

# ---------------------------------------------------
# CLl / Parser
# ---------------------------------------------------

def main():
    parser = argparse.ArgumentParser(prog="vpn")
    sub = parser.add_subparsers(dest="cmd")

    # init
    p_init = sub.add_parser("init")
    p_init.add_argument("--endpoint", required=False)
    p_init.add_argument("--port", type=int, default=51820)
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

    p_export = sub.add_parser("export-peer")
    p_export.add_argument("name")
    p_export.set_defaults(func=cmd_export_peer)

    # generate-qr
    p_qr = sub.add_parser("generate-qr")
    p_qr.add_argument("name")
    p_qr.set_defaults(func=cmd_generate_qr)

    # parse
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
