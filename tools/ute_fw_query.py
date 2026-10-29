"""Ask UTE's update server which firmware files exist for a watch (see docs/TechLife-S100.md §7b.7).

Reproduces realme Fit's request: POST form field `content` = RSA-encrypted JSON
(RSA/ECB/PKCS1Padding with the app's public key, 32-char chunks, base64, newlines stripped).
Prints the server's JSON reply; downloading any listed URL is left to the user.

Usage:
    python tools/ute_fw_query.py [btname] [versionname] [endpoint]
    defaults: RH288A V000000 getBtVersionUpdate   (TechLife S100 reports RH288AV001319)
"""
from __future__ import annotations
import base64
import json
import os
import sys
import urllib.parse
import urllib.request

BASE_URL = "https://apsouth.uteasy.com/ci-yc/index.php/api/client/"
APP_KEY = "acd3e73149ae3ab48cf8775dc4afa9fc"  # YCAPPKEY from realme Fit 1.2.9 manifest
PUBLIC_KEY_B64 = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC57TJWQJc+vSp+Lq5ctZIhT3tZAWJMsgHLexnPUkix6ci52M9lIKgl"
    "wthipBlExFs8TN/1eY6Y56oJce+AMlIakVEg+UZJ1kHFRDwzJdpG/Lb8hi61fknkhROu6sB3xcG9jUWpWTLRl3KTAd4A"
    "GiEgPdDS3bdA+oFr6lygvj9SlQIDAQAB"
)


def _der_items(buf: bytes, off: int = 0):
    """Yield (tag, content_start, content_end) for consecutive DER items."""
    while off < len(buf):
        tag = buf[off]
        length = buf[off + 1]
        off += 2
        if length & 0x80:
            n = length & 0x7F
            length = int.from_bytes(buf[off:off + n], "big")
            off += n
        yield tag, off, off + length
        off += length


def _load_public_key(b64: str) -> tuple[int, int]:
    der = base64.b64decode(b64)
    _, s, e = next(_der_items(der))                       # SubjectPublicKeyInfo
    items = list(_der_items(der[s:e]))
    _, bs, be = items[1]                                  # BIT STRING
    rsa = der[s:e][bs + 1:be]                             # skip unused-bits byte
    _, s2, e2 = next(_der_items(rsa))                     # RSAPublicKey SEQUENCE
    (_, ns, ne), (_, es, ee) = list(_der_items(rsa[s2:e2]))
    body = rsa[s2:e2]
    return int.from_bytes(body[ns:ne], "big"), int.from_bytes(body[es:ee], "big")


def _rsa_pkcs1_encrypt(msg: bytes, n: int, e: int) -> bytes:
    k = (n.bit_length() + 7) // 8
    pad_len = k - len(msg) - 3
    pad = bytearray()
    while len(pad) < pad_len:
        pad += bytes(b for b in os.urandom(pad_len) if b)
    block = b"\x00\x02" + bytes(pad[:pad_len]) + b"\x00" + msg
    return pow(int.from_bytes(block, "big"), e, n).to_bytes(k, "big")


def encrypt_for_split_for_chinese(text: str) -> str:
    n, e = _load_public_key(PUBLIC_KEY_B64)
    chunks = [text[i:i + 32] for i in range(0, len(text), 32)]
    return "".join(base64.b64encode(_rsa_pkcs1_encrypt(c.encode(), n, e)).decode() for c in chunks)


def query(endpoint: str, payload: dict) -> str:
    body = urllib.parse.urlencode({"content": encrypt_for_split_for_chinese(json.dumps(payload, separators=(",", ":")))})
    req = urllib.request.Request(BASE_URL + endpoint, data=body.encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


if __name__ == "__main__":
    btname = sys.argv[1] if len(sys.argv) > 1 else "RH288A"
    version = sys.argv[2] if len(sys.argv) > 2 else "V000000"
    endpoint = sys.argv[3] if len(sys.argv) > 3 else "getBtVersionUpdate"
    key = "versioncode" if endpoint == "getPatchlicationUpdate" else "versionname"
    print(query(endpoint, {"appkey": APP_KEY, "btname": btname, key: version, "debug": 1}))
