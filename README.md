# RiseupVPN-ProxyPool

来源：`RiseupVPN-Android-latest.apk`（`se.leap.riseupvpn` 1.7.1，LEAP / bitmask 客户端，开源）。

Riseup VPN 是公民社会公益 VPN，节点为 16 台自建 OpenVPN 网关。本仓库从 APK 内置 provider 还原接入协议，直接调用其**公开匿名接口**拿到客户端证书，产出 15 份可直连的 `.ovpn`。

## 状态

| 模块 | 状态 | 依据 |
|---|---|---|
| APK 结构画像 | 已验证 | `se.leap.riseupvpn` 1.7.1，libgojni（bitmask Go 核心）+ libopenvpn + libtor |
| provider 定位 | 已验证 | `assets/riseup.net.json` + `assets/urls/riseup.net.url` |
| API 端点 | 已验证 | `https://api.black.riseup.net:4430/3/config/eip-service.json`，200 / 7813 B |
| 证书获取 | 已验证 | `GET /3/cert` 免认证返回 RSA 私钥 + 客户端证书（`allow_anonymous: true`） |
| 网关清单 | 已验证 | 16 台，含 host / ip / location / 端口矩阵 |
| OpenVPN 握手 | 已验证 | 32 份配置中 **15 份完成 TLS + PUSH_REPLY** |
| 配置生成 | 已验证 | `tools/build_ovpn.py` 一次拉齐 eip + 匿名证书 + ca，产出 32 份 .ovpn |
| 池接入文档 | 已验证 | `docs/NEWAPI_INTEGRATION.md`（tun2socks 链路、三套方案、节点表） |

## 关键事实

```
包名          se.leap.riseupvpn
版本          1.7.1
内核          libgojni.so (bitmask Go, 31 MB) + libopenvpn + libtor (内置 Tor)
provider      assets/riseup.net.json
API           https://api.black.riseup.net:4430          ← 注意端口 4430
API 版本      3
CA            https://black.riseup.net/ca.crt           (LEAP Root CA, 2026-11-03 签发)
GeoIP         https://menshen.riseup.net/json
MOTD          https://static.riseup.net/vpn/motd.json
服务类型      openvpn only
注册策略      enrollment_policy: open, allow_anonymous: true
```

`riseup.net` 系域名在墙内被 DNS 污染（解析到 Facebook IP：`157.240.x` / `31.13.x`）。`api.black.riseup.net` 的真实 IP 走 DoH 可拿到 `162.220.12.226`，但该 IP 对境内和商业 VPN 出口均超时；**经加拿大节点访问 4430 端口才通**。

## 网关（16 台，★ = OpenVPN 握手实测通过）

| 主机 | IP | 地区 | 端口 | 实测 |
|---|---|---|---|---|
| vpn02-par | 51.159.197.108 | Paris | 53/80/1194 | — |
| vpn03-par | 163.172.20.106 | Paris | 53/80/1194 | ★ tcp80 / udp1194 |
| vpn04-ams | 51.15.9.205 | Amsterdam | 53/80/1194 | ★ udp1194 |
| vpn05-par | 195.154.119.165 | Paris | 53/80/1194 | ★ tcp80 / udp1194 |
| vpn06-ams | 51.158.144.32 | Amsterdam | 53/80/1194 | ★ tcp80 |
| vpn07-par | 163.172.83.106 | Paris | 53/80/1194 | — |
| vpn08-par | 51.159.28.229 | Paris | 53/80/1194 | ★ udp1194 |
| vpn10-mtl | 199.58.83.11 | Montreal | 53/80/1194 | — |
| vpn11-par | 51.159.55.86 | Paris | 53/80/1194 | ★ tcp80 / udp1194 |
| vpn13-ams | 51.158.144.31 | Amsterdam | 53/80/1194 | ★ udp1194 |
| vpn14-par | 51.159.196.108 | Paris | 53/80/1194 | ★ tcp80 |
| vpn18-mtl | 199.58.83.9 | Montreal | 53/80/1194 | ★ tcp80 / udp1194 |
| vpn20-par | 51.159.198.167 | Paris | 53/80/1194 | — |
| vpn21-par | 163.172.20.108 | Paris | 53/80/1194 | ★ tcp80 |
| vpn22-mia | 89.187.173.169 | Miami | 53/80/1194 | ★ tcp80 |
| vpn23-mia | 89.187.173.174 | Miami | 53/80/1194 | — |

直连 TCP 可达性：**20/48 端口通**（延迟 240–310 ms），其中 `vpn05` / `vpn06` / `vpn11` / `vpn18` 三端口全通。

## 用法

```bash
# 一次拉齐：eip-service.json + 匿名证书 + ca.crt + 32 份 .ovpn
python tools/build_ovpn.py                    # 直连 4430
python tools/build_ovpn.py 127.0.0.1:22010    # 域名被墙时走本地 socks

# 批量握手验证（--dev null，不建隧道、不改路由、不需要管理员权限）
python tools/probe_ovpn.py
```

生成的 `data/ovpn/*.ovpn` 内嵌 `<ca><cert><key>`，任意 OpenVPN 客户端可直接用。
仓库**不提交**私钥与二进制客户端（`.gitignore` 已排除），需要客户端就去 openvpn.net 装，或用你自己的现有客户端。

## 为什么选 Riseup

- **固定 IP**，不是商业 VPN 的 NAT 轮换出口 → 适合长期稳定的业务出口
- 网关端口开放 **53 / 80 / 1194**，53 和 80 在多数受限网络里可出
- 匿名证书**不需要注册**：`GET /3/cert` 直接返回，随便换
- 公益基础设施，无计费、无广告、无账号

## 限制

- 32 份配置里 17 份未完成握手（TLS 阶段失败），多为端口过滤或网关当前不可用
- 仓库不含私钥：`data/client.pem` 与 `data/ovpn/` 被 `.gitignore` 排除，跑一次 `build_ovpn.py` 即可生成
- 证书为共享匿名证书，**所有人拿到的都是同一 CA 下的新签证书**；不承担匿名性承诺以外的合规义务
- 需管理员权限才能创建 TUN 适配器；`--dev null` 验证仅证明控制通道可用，不代表数据面已通
- Riseup 禁止用于滥用行为，服务条款见 riseup.net
