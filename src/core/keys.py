import subprocess

def generate_private_key():
    return subprocess.check_output(["wg", "genkey"]).decode().strip()

def private_to_public(private_key):
    proc = subprocess.Popen(
        ["wg", "pubkey"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE
    )
    pub, _ = proc.communicate(private_key.encode())
    return pub.decode().strip()

def generate_keypair():
    priv = generate_private_key()
    pub = private_to_public(priv)
    return priv, pub
