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

### 3. Show VPN status

```sh
vpn status
```

Displays:
- interface state
- WireGuard runtime information (`wg show`)

---

### 4. Export configuration files (debug / manual use)

```sh
vpn export
```

Outputs:

```
configs/<interface>.conf
```

Useful for inspection or manual deployment, without modifying the system.

---

### 5. Apply the server configuration (root required)

```sh
sudo vpn apply
```

This command:
- validates the internal state
- installs `/etc/wireguard/<interface>.conf` safely
- backs up any existing configuration
- brings the interface up using `wg-quick`

---

### 6. Enable / disable the tunnel

```sh
sudo vpn enable
sudo vpn disable
```

Equivalent to:

```sh
wg-quick up <interface>
wg-quick down <interface>
```

but guarded by internal state validation.

---

### 7. Generate a QR code for a peer (mobile)

```sh
vpn qr alice
```

Creates:

```
configs/alice.png
```

Scannable by the WireGuard Android / iOS app.

---

### 8. Diagnostics

```sh
vpn doctor
```

Checks:
- required binaries (`wg`, `wg-quick`, `ip`)
- state file presence
- `/etc/wireguard` setup
- IP forwarding
- configuration sanity

---

## Notes

- Client configurations always include a valid `Endpoint` with port
- IPv6 endpoints are automatically bracketed
- Firewall and NAT configuration are intentionally left to the user
