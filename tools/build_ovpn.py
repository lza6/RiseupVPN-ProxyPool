#!/usr/bin/env python3
"""Riseup VPN: 从公开 API 拉 eip-service.json + 匿名客户端证书, 生成可直接用的 .ovpn 配置.

用法:
    python tools/build_ovpn.py                 # 直连 api.black.riseup.net:4430
    python tools/build_ovpn.py 127.0.0.1:22010 # 经本地 socks5（域名被污染时用）
"""
import json, os, re, socket, ssl, struct, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
API_HOST, API_PORT = "api.black.riseup.net", 4430
PROXY = None
if len(sys.argv) > 1 and ":" in sys.argv[1]:
    h, p = sys.argv[1].rsplit(":", 1)
    PROXY = (h, int(p))

def _connect(timeout=30):
    if PROXY:
        s = socket.create_connection(PROXY, timeout); s.settimeout(timeout)
        s.sendall(b"\x05\x01\x00")
        if s.recv(2) != b"\x05\x00": raise IOError("socks auth failed")
        hb = API_HOST.encode()
        s.sendall(b"\x05\x01\x00\x03" + bytes([len(hb)]) + hb + struct.pack("!H", API_PORT))
        r = s.recv(4)
        if len(r) < 4 or r[1] != 0: raise IOError("socks rep=%d" % (r[1] if len(r) > 1 else -1))
        at = r[3]
        if at == 1: s.recv(4)
        elif at == 3: s.recv(s.recv(1)[0])
        elif at == 4: s.recv(16)
        s.recv(2)
    else:
        s = socket.create_connection((API_HOST, API_PORT), timeout); s.settimeout(timeout)
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    return ctx.wrap_socket(s, server_hostname=API_HOST)

def _read(ss, timeout=30):
    ss.settimeout(timeout)
    d = b""
    while True:
        c = ss.recv(16384)
        if not c: break
        d += c
    ss.close()
    i = d.find(b"\r\n\r\n")
    head, body = d[:i].decode("utf-8", "replace"), d[i + 4:]
    if "chunked" in head.lower():
        out, p = b"", 0
        while p < len(body):
            j = body.find(b"\r\n", p)
            if j < 0: break
            try: n = int(body[p:j], 16)
            except ValueError: break
            p = j + 2
            if n == 0: break
            out += body[p:p + n]; p += n + 2
        body = out
    return body

def api_get(path, timeout=30):
    ss = _connect(timeout)
    ss.sendall(("GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: bitmask\r\nConnection: close\r\n\r\n" % (path, API_HOST)).encode())
    return _read(ss, timeout)

def fetch_ca(timeout=30):
    s = socket.create_connection(("black.riseup.net", 443), timeout); s.settimeout(timeout)
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    ss = ctx.wrap_socket(s, server_hostname="black.riseup.net")
    ss.sendall(b"GET /ca.crt HTTP/1.1\r\nHost: black.riseup.net\r\nConnection: close\r\n\r\n")
    return _read(ss, timeout)

def refresh():
    os.makedirs(DATA, exist_ok=True)
    eip = json.loads(api_get("/3/config/eip-service.json"))
    json.dump(eip, open(os.path.join(DATA, "eip-service.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(DATA, "client.pem"), "wb").write(api_get("/3/cert"))
    open(os.path.join(DATA, "ca.crt"), "wb").write(fetch_ca())
    print("refreshed: data/eip-service.json, data/client.pem, data/ca.crt")

def pem_blocks(txt):
    return {m.group(1): m.group(0) for m in re.finditer(r"-----BEGIN ([A-Z ]+)-----.*?-----END \1-----", txt, re.S)}

def main():
    os.makedirs(DATA, exist_ok=True)
    if "--fetch" in sys.argv or not os.path.exists(os.path.join(DATA, "client.pem")):
        refresh()
    eip = json.load(open(os.path.join(DATA, "eip-service.json"), encoding="utf-8"))
    certs = pem_blocks(open(os.path.join(DATA, "client.pem"), encoding="utf-8").read())
    ca = open(os.path.join(DATA, "ca.crt"), encoding="utf-8").read().strip()
    key, cert = certs["RSA PRIVATE KEY"], certs["CERTIFICATE"]
    conf = eip.get("openvpn_configuration", {})
    outdir = os.path.join(DATA, "ovpn"); os.makedirs(outdir, exist_ok=True)
    made = []
    for g in eip["gateways"]:
        tr = next((t for t in g["capabilities"]["transport"] if t["type"] == "openvpn"), None)
        if not tr: continue
        for proto in ("tcp", "udp"):
            if proto not in tr["protocols"]: continue
            port = "80" if proto == "tcp" else "1194"
            if port not in tr["ports"]: port = tr["ports"][0]
            body = [
                "client", "dev tun", "proto %s" % proto, "remote %s %s" % (g["ip_address"], port),
                "resolv-retry infinite", "nobind", "persist-key", "persist-tun",
                "auth %s" % conf.get("auth", "SHA512"),
                "cipher %s" % conf.get("cipher", "AES-256-GCM"),
                "data-ciphers %s" % conf.get("data-ciphers", "AES-256-GCM"),
                "tls-cipher %s" % conf.get("tls-cipher", "TLS-ECDHE-ECDSA-WITH-AES-256-GCM-SHA384"),
                "tls-version-min 1.2", "remote-cert-tls server", "verb 3",
                "<ca>", ca, "</ca>", "<cert>", cert, "</cert>", "<key>", key, "</key>",
            ]
            name = "%s-%s-%s%s.ovpn" % (g["location"].lower(), g["host"].split(".")[0], proto, port)
            open(os.path.join(outdir, name), "w", encoding="utf-8").write("\n".join(body) + "\n")
            made.append((name, g["ip_address"], port, proto))
    print("生成 %d 份配置 -> %s" % (len(made), outdir))

if __name__ == "__main__":
    main()
