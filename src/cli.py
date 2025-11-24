import argparse
import os

from core.keys import generate_keypair
from core.state import (
    set_server, add_client, find_next_ip,
    get_server, get_clients, remove_client
)
from core.config_builder import generate_server_config, generate_client_config


def create_client(name, dns=None):
    """
    Fonction centrale pour créer un client :
    - génère clés
    - trouve IP dispo
    - ajoute au state
    """
    priv, pub = generate_keypair()
    ip = find_next_ip()

    client = {
        "name": name,
        "ip": ip,
        "private_key": priv,
        "public_key": pub,
        "dns": dns
    }

    add_client(client)
    return client


def cmd_init_server(args):
    priv, pub = generate_keypair()

    server = {
        "ip": "10.8.0.1",
        "subnet": 24,
        "private_key": priv,
        "public_key": pub,
        "endpoint": args.endpoint,
        "port": args.port
    }

    set_server(server)
    print("[OK] Serveur initialisé.")


def cmd_add_client(args):
    client = create_client(args.name, dns=args.dns)
    print(f"[OK] Client ajouté : {client['name']} ({client['ip']})")


def cmd_list(args):
    server = get_server()
    clients = get_clients()

    print("=== Serveur ===")
    if server:
        print(f"IP        : {server['ip']}/{server['subnet']}")
        print(f"Endpoint  : {server['endpoint']}:{server['port']}\n")
    else:
        print("Aucun serveur configuré.\n")

    print("=== Clients ===")
    if not clients:
        print("Aucun client.")
    else:
        for c in clients:
            print(f"- {c['name']} ({c['ip']})")


def cmd_generate_configs(args):
    server = get_server()
    clients = get_clients()

    if not server:
        print("Erreur : serveur non initialisé.")
        return

    os.makedirs("configs/clients", exist_ok=True)

    # SERVER
    server_conf = generate_server_config(server, clients)
    with open("configs/server.conf", "w") as f:
        f.write(server_conf)

    # CLIENTS
    for client in clients:
        conf = generate_client_config(client, server)
        path = f"configs/clients/{client['name']}.conf"
        with open(path, "w") as f:
            f.write(conf)

    print("[OK] Fichiers générés dans ./configs/")


def cmd_remove_client(args):
    removed = remove_client(args.name)
    if not removed:
        return

    path = f"configs/clients/{args.name}.conf"
    if os.path.exists(path):
        os.remove(path)

    print(f"[OK] Client supprimé : {args.name}")


import qrcode

def cmd_generate_qr(args):
    server = get_server()
    clients = get_clients()

    client = next((c for c in clients if c["name"] == args.name), None)
    if not client:
        print("Client introuvable.")
        return

    conf = generate_client_config(client, server)

    img = qrcode.make(conf)
    path = f"configs/clients/{client['name']}.png"
    img.save(path)

    print(f"[OK] QR code généré : {path}")
#
# ----------------------------
# Parser CLI
# ----------------------------

def main():
    parser = argparse.ArgumentParser(prog="vpn")
    sub = parser.add_subparsers(dest="cmd")

    # init-server
    p_init = sub.add_parser("init-server")
    p_init.add_argument("--endpoint", required=True)
    p_init.add_argument("--port", type=int, default=51820)
    p_init.set_defaults(func=cmd_init_server)

    # add-client
    p_add = sub.add_parser("add-client")
    p_add.add_argument("name")
    p_add.set_defaults(func=cmd_add_client)

    # list
    p_list = sub.add_parser("list")
    p_list.set_defaults(func=cmd_list)

    # remove-client
    p_rm = sub.add_parser("remove-client")
    p_rm.add_argument("name")
    p_rm.set_defaults(func=cmd_remove_client)

    p_qr = sub.add_parser("generate-qr")
    p_qr.add_argument("name")
    p_qr.set_defaults(func=cmd_generate_qr)

    # generate-configs
    p_gen = sub.add_parser("generate-configs")
    p_gen.set_defaults(func=cmd_generate_configs)

    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
