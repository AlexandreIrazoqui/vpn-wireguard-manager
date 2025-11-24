## WireGuard configuration structure

This project uses the minimal WireGuard config.
Example files are provided in: 
- `wireguard/server/wg0.conf.example`
- `wireguard/client/client.conf.example`

The keys are meant to be private, this repository will generate them.


## Installation

### Step 1 : Clone the repository

```sh
git clone https://github.com/<YOUR_USERNAME>/ProjetVPN.git
cd ProjetVPN
```

### Step 2: Create a virtual environment 
```sh 
python -m venv venv
source venv/bin/activate
```
### Step 3: Install dependencies
```sh
pip install -r requirements.txt
```
### Step 4: install the VPN cli (optionnal)

```sh 
sudo cp vpn /usr/local/bin/vpn
sudo chmod +x /usr/local/bin/vpn
```



## 🧪 Usage

### 1. Initialize the server

```sh
vpn init-server --endpoint <YOUR_PUBLIC_IP> --port 51820
```

This generates server keys and saves the WireGuard server configuration to `state.json`.

---

### 2. Add a client

```sh
vpn add-client alice
```

With a custom DNS:

```sh
vpn add-client alice --dns 1.1.1.1
```

---

### 3. List server and clients

```sh
vpn list
```

---

### 4. Remove a client

```sh
vpn remove-client alice
```

Removes the client from state and deletes its generated `.conf` file.

---

### 5. Generate WireGuard configuration files

```sh
vpn generate-configs
```

Outputs:

```
configs/server.conf
configs/clients/<client>.conf
```

---

### 6. Generate QR code for mobile import

```sh
vpn generate-qr alice
```

Creates:

```
configs/clients/alice.png
```

Scannable by the WireGuard Android/iOS app.

---




