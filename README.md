# ProjetVPN – WireGuard VPN Manager

## WireGuard configuration structure

This project provides a minimal WireGuard VPN manager with a CLI interface.

WireGuard configurations are generated dynamically from an internal state file (`data/state.json`).
The tool can:
- generate server and client keys
- allocate client IPs automatically
- render WireGuard configs
- safely install the server configuration into `/etc/wireguard`
- bring the tunnel up and down
- enable a basic iptables firewall/NAT ruleset for VPN routing

All keys are generated locally and are meant to stay private.

---

## Installation

### Step 1: Clone the repository

```sh
git clone https://github.com/<YOUR_USERNAME>/ProjetVPN.git
cd ProjetVPN
```

---

### Step 2: Create a virtual environment

```sh
python -m venv venv
source venv/bin/activate
```

---

### Step 3: Install dependencies

```sh
pip install -r requirements.txt
```

---

### Step 4: Install the VPN CLI (optional)

This allows calling `vpn` directly instead of `python src/cli.py`.

```sh
sudo cp vpn /usr/local/bin/vpn
sudo chmod +x /usr/local/bin/vpn
```

---

## Usage

### 1. Initialize the WireGuard server

```sh
vpn init --endpoint <YOUR_PUBLIC_IP_OR_DNS> --port 51820
```

This command:
- generates the server keypair
- initializes the VPN network (default: `10.8.0.0/24`)
- assigns the server address (e.g. `10.8.0.1/24`)
- creates `data/state.json`

This command does **not** touch `/etc/wireguard`.

---

### 2. Add a peer (client)

```sh
vpn add-peer alice
```

This:
- allocates a free IP automatically (e.g. `10.8.0.2/32`)
- generates client keys
- updates `data/state.json`

---

### 3. List peers

```sh
vpn list-peers
```

---

### 4. Export configuration files (debug / manual use)

Export one peer config:

```sh
vpn export-peer alice
```

Export all peers:

```sh
vpn export-all
```

This writes:

```
configs/<peer>.conf
```

---

### 5. Generate a QR code for a peer (mobile)

```sh
vpn generate-qr alice
```

Creates:

```
configs/alice.png
```

Scannable by the WireGuard Android / iOS app.

---

### 6. Apply the server configuration (root required)

```sh
sudo vpn apply
```

This command:
- validates the internal state
- installs `/etc/wireguard/<interface>.conf` safely
- backs up any existing configuration
- restarts the interface using `wg-quick` (unless `--no-restart`)

Disable restart:

```sh
sudo vpn apply --no-restart
```

---

### 7. Enable / disable the tunnel

```sh
sudo vpn enable
sudo vpn disable
```

You can override the interface:

```sh
sudo vpn enable --iface wg0
sudo vpn disable --iface wg0
```

---

### 8. Show VPN status

```sh
vpn status
```

---

### 9. Firewall / NAT (iptables)

If you want routed VPN traffic (client -> internet), you typically need:
- IP forwarding enabled
- NAT (masquerade) + forwarding rules

This project provides a simple iptables-based ruleset:

Enable firewall + NAT:

```sh
sudo vpn firewall enable
```

If WAN interface detection fails, specify it:

```sh
sudo vpn firewall enable --wan eth0
# or: --wan enp3s0 / wlp2s0 ...
```

Status:

```sh
vpn firewall status
```

Verbose status (prints ruleset when available):

```sh
vpn firewall status --verbose
```

Disable:

```sh
sudo vpn firewall disable
```

Notes:
- This firewall setup is intentionally minimal (focused on WireGuard + NAT).
- Persistence across reboot depends on your distro (iptables rules are not always persistent by default).

---

### 10. Diagnostics

```sh
vpn doctor
```

Checks:
- required binaries (`wg`, `wg-quick`, `ip`)
- state file presence
- `/etc/wireguard` setup
- IP forwarding
- configuration sanity
- hints about root usage

---

## Notes

- Client configurations always include a valid `Endpoint` with port
- IPv6 endpoints are automatically bracketed
