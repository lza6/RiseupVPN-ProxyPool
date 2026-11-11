#!/usr/bin/env python3
"""用 openvpn --dev null 验证 Riseup 网关是否完成控制通道握手 (不建隧道, 不改路由)."""
import os, re, subprocess, sys, glob, json, concurrent.futures as cf

OVPN = r"C:\ev_tmp\ovpn_x\bin.openvpn.exe"
DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ovpn")

def probe(path, timeout=14):
    cmd = [OVPN, "--config", path, "--dev", "null", "--verb", "3",
           "--connect-retry-max", "1", "--connect-timeout", "6",
           "--ping-exit", "8", "--windows-driver", "wintun"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        out = (r.stdout + r.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"") + (e.stderr or b"")).decode("utf-8", "replace")
    ok = "PUSH_REPLY" in out
    cn = re.search(r"CN=(\S+)", out)
    ip = re.search(r"Peer Connection Initiated with \[AF_INET\](\S+)", out)
    err = ""
    for line in out.splitlines():
        if "Exiting due to fatal error" in line or "AUTH_FAILED" in line or "TLS Error" in line:
            err = line.strip()[:80]
    return {"file": os.path.basename(path), "ok": ok,
            "cn": cn.group(1) if cn else None,
            "peer": ip.group(1) if ip else None, "err": err}

def main():
    files = sorted(glob.glob(os.path.join(DIR, "*.ovpn")))
    res = []
    with cf.ThreadPoolExecutor(4) as ex:
        for r in ex.map(probe, files):
            res.append(r)
            print(f'{r["file"]:<34} {"OK" if r["ok"] else "FAIL":<5} {r["peer"] or "":<22} {r["err"]}', flush=True)
    json.dump(res, open(os.path.join(os.path.dirname(DIR), "ovpn_probe.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f'\n握手成功 {sum(1 for r in res if r["ok"])}/{len(res)}')

if __name__ == "__main__":
    main()
