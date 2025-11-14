from core.config_builder import generate_server_config, generate_client_config

server_conf = generate_server_config(server, [client])
client_conf = generate_client_config(client, server)

with open("configs/server.conf", "w") as f:
    f.write(server_conf)

with open(f"configs/clients/{client['ip']}.conf", "w") as f:
    f.write(client_conf)
