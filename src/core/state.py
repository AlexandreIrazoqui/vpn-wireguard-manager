import json
import os

STATE_FILE = "state.json"


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"server": None, "clients": []}
    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)


def set_server(server_dict):
    state = load_state()
    state["server"] = server_dict
    save_state(state)


def get_server():
    state = load_state()
    return state["server"]



def add_client(client_dict):
    state = load_state()
    state["clients"].append(client_dict)
    save_state(state)


def get_clients():
    state = load_state()
    return state["clients"]

def find_next_ip():
    state = load_state()
    used_ips = {client["ip"] for client in state["clients"]}

    base = "10.8.0."
    for i in range(2, 255):
        candidate = base + str(i)
        if candidate not in used_ips:
            return candidate

    raise RuntimeError("No ip available in the subnet")

def remove_client(name):
    state = load_state()
    clients = state["clients"]

    new_clients = [c for c in clients if c["name"] != name]

    if len(new_clients) == len(clients):
        print(f"Aucun client nommé '{name}'.")
        return False

    state["clients"] = new_clients
    save_state(state)
    return True
