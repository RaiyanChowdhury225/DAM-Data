"""
fetch_chain.py — build a CA bundle for hosts that omit their intermediate.

dam.gov.bd sends only its own certificate, so Python cannot build a chain to a
trusted root. The certificate's Authority Information Access extension names the
issuer's certificate; we download it and append it to the certifi bundle.

    python fetch_chain.py            -> data/dam_chain.pem
"""
import os
import socket
import ssl
import sys
import tempfile
from pathlib import Path

import certifi
import requests

HOST = sys.argv[1] if len(sys.argv) > 1 else "dam.gov.bd"
OUT = Path(__file__).resolve().parent / "data" / "dam_chain.pem"


def leaf_info(host):
    """Fetch the server's certificate without verifying it, and parse it."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, 443), timeout=20) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
        f.write(ssl.DER_cert_to_PEM_cert(der))
        path = f.name
    try:
        return ssl._ssl._test_decode_cert(path)
    finally:
        os.unlink(path)


info = leaf_info(HOST)
# caIssuers holds the URL of the issuing certificate (plain HTTP, so no chicken-and-egg)
urls = [u for u in info.get("caIssuers", ()) if u.startswith("http")]
if not urls:
    sys.exit("No caIssuers URL in the certificate - download the intermediate manually.")

print("intermediate URL:", urls[0])
data = requests.get(urls[0], timeout=30).content
# these are usually DER (.crt); convert if it is not already PEM
pem = data.decode() if data.lstrip().startswith(b"-----") else ssl.DER_cert_to_PEM_cert(data)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(Path(certifi.where()).read_text() + "\n" + pem, encoding="utf-8")
print(f"wrote {OUT}")

# prove it works
r = requests.get(f"https://{HOST}", timeout=30, verify=str(OUT))
print("verification test:", r.status_code)