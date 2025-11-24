import os

SERVER_TEMPLATE = """[Interface]
Address = {server_ip}/{subnet}
PrivateKey = {server_private_key}
ListenPort = {listen_port}

# Clients
{peers}
"""

PEER_TEMPLATE = """[Peer]
PublicKey = {public_key}
AllowedIPs = {client_ip}/32
"""

CLIENT_TEMPLATE = """[Interface]
Address = {client_ip}/32
PrivateKey = {client_private_key}
{dns_block}[Peer]
PublicKey = {server_public_key}
Endpoint = {endpoint}:{port}
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
"""

def generate_server_config(server, clients):
    peers_blocks = "\n".join(
        PEER_TEMPLATE.format(
            public_key=c["public_key"],
            client_ip=c["ip"]
        ) for c in clients
    )

    return SERVER_TEMPLATE.format(
        server_ip=server["ip"],
        subnet=server["subnet"],
        server_private_key=server["private_key"],
        listen_port=server["port"],
        peers=peers_blocks
    )

def generate_client_config(client, server):
    dns_block = f"DNS = {client['dns']}\n" if client.get("dns") else ""
    return CLIENT_TEMPLATE.format(
        client_ip=client["ip"],
        client_private_key=client["private_key"],
        server_public_key=server["public_key"],
        endpoint=server["endpoint"],
        port=server["port"],
        dns_block=dns_block
    )
