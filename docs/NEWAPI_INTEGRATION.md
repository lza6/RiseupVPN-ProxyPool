# RiseupVPN → new-api 代理池对接指南

> 面向对接会话。Riseup 是公益 VPN，节点为该组织自建基础设施，条款见 riseup.net。
> 本仓库只负责还原协议与生成配置，线上决策由对接方做。

---

## 1. 先说结论：链路比 EdgeVPN 长一环

节点是 **OpenVPN**（三层隧道），new-api 只会说 SOCKS5。中间必须是：

```
new-api ──> socks5://127.0.0.1:25001 ──> tun2socks ──> tun 设备 ──> openvpn ──> Riseup 网关
                    (本地监听)            (socks5→tun)   (点对点)     (UDP/TCP)
```

**关键**：`hev-socks5-tunnel` 也是同样的方向（socks5 → tun），SuperVPN 的 APK 里就带这个 so。
一个节点 = 一套 `openvpn 进程 + tun2socks 进程 + 一个 socks 端口`。

## 2. 三条可选路线

| 方案 | 做法 | 适用 | 代价 |
|---|---|---|---|
| **A. tun2socks**（推荐） | 每网关一个 `openvpn --config` + 一个 `tun2socks -device tunN -proxy socks5://127.0.0.1:PORT` | Windows / Linux 都能跑 | 每节点 2 个进程；需要 TAP/wintun 驱动 |
| B. hev-socks5-tunnel | 同上但用 hev 的实现 | Linux / Docker 首选（Android APK 同款） | Windows 无官方 release，需自行编译 |
| C. 不进 new-api | OpenVPN 客户端直接建隧道 + 业务侧按目标 IP 分流（`--route-nopull` + 自定义 route） | 需要**固定出口 IP** 的业务（账号绑定、白名单） | 不能做多节点轮换 |

## 3. 落地步骤（方案 A）

### 3.1 生成配置

```powershell
# 拉 eip-service.json + 匿名客户端证书 + ca.crt，生成 data/ovpn/*.ovpn
python tools\build_ovpn.py

# 若 api.black.riseup.net:4430 被墙，先起一个本地 socks 再跑：
python tools\build_ovpn.py 127.0.0.1:22010
```

`/3/cert` **免认证**，每次调用返回一套新的匿名证书（同一 LEAP CA 签发）。配置内嵌 `<ca><cert><key>`，无需额外文件。

### 3.2 逐节点建隧道 + 转 socks

Windows（openvpn 2.7 + wintun）：

```powershell
# 节点 1
Start-Process tools\openvpn\openvpn.exe -ArgumentList `
  '--config data\ovpn\paris-vpn05-par-tcp80.ovpn','--dev tun11','--route-nopull'
# tun2socks（xjasonlyu/tun2socks，选 wintun 版）
Start-Process tun2socks.exe -ArgumentList '-device tun11','-proxy socks5://127.0.0.1:25001','-interface tun11'

# 节点 2 同理：--dev tun12 / -proxy socks5://127.0.0.1:25002
```

**`--route-nopull` 必须加**：默认配置会下推 `redirect-gateway def1`，抢走整机默认路由，直接违反「不影响本机现有代理」的约束。加了之后只有 tun 设备建起来，路由由 tun2socks 显式接管。

Linux / Docker：

```bash
openvpn --config data/ovpn/paris-vpn05-par-tcp80.ovpn --dev tun11 --route-nopull --daemon
hev-socks5-tunnel /etc/hev/tun11.yml   # tun-name: tun11, socks5.listen: 127.0.0.1:25001
```

### 3.3 生成池文件

```
socks5://127.0.0.1:25001
socks5://127.0.0.1:25002
...
```

写进 new-api：

```bash
export TRYINGOPEN_PROXY_FILE=/abs/path/to/riseup_proxies.txt
curl -X POST http://<new-api>/api/twoapi_panel/proxy_pool/reload
```

解析规则与 EdgeVPN 文档一致：逐行整行 `url.Parse`、只跳过 `#` 开头整行、白名单 `http/https/socks5/socks5h`、卡片名取 `filepath.Base`。

**Docker 部署注意**：tun 设备在容器内不可用，要么用 `--privileged --cap-add NET_ADMIN` 起同一容器，要么把 openvpn+tun2socks 放在宿主机、new-api 容器用宿主 IP 访问。

## 4. 节点清单与实测

16 台网关，★ = OpenVPN 控制通道实测通过（`TLS1.3 + PUSH_REPLY`）：

| 主机 | IP | 地区 | 端口 | 实测 |
|---|---|---|---|---|
| vpn03-par | 163.172.20.106 | Paris | 53/80/1194 | ★ tcp80 / udp1194 |
| vpn05-par | 195.154.119.165 | Paris | 53/80/1194 | ★ tcp80 / udp1194 |
| vpn08-par | 51.159.28.229 | Paris | 53/80/1194 | ★ udp1194 |
| vpn11-par | 51.159.55.86 | Paris | 53/80/1194 | ★ tcp80 / udp1194 |
| vpn14-par | 51.159.196.108 | Paris | 53/80/1194 | ★ tcp80 |
| vpn21-par | 163.172.20.108 | Paris | 53/80/1194 | ★ tcp80 |
| vpn04-ams | 51.15.9.205 | Amsterdam | 53/80/1194 | ★ udp1194 |
| vpn06-ams | 51.158.144.32 | Amsterdam | 53/80/1194 | ★ tcp80 |
| vpn13-ams | 51.158.144.31 | Amsterdam | 53/80/1194 | ★ udp1194 |
| vpn18-mtl | 199.58.83.9 | Montreal | 53/80/1194 | ★ tcp80 / udp1194 |
| vpn22-mia | 89.187.173.169 | Miami | 53/80/1194 | ★ tcp80 |

未通过的 5 台（vpn02 / vpn07 / vpn10 / vpn20 / vpn23）多为端口过滤，可稍后重测。

直连 TCP 可达性：**20/48 端口通**，延迟 240–310 ms。`vpn05` / `vpn06` / `vpn11` / `vpn18` 三端口全通。

## 5. 为什么值得单独做一条池

| 维度 | EdgeVPN (astroapps) | Riseup |
|---|---|---|
| 出口 IP | NAT 池，入口 ≠ 出口，会漂 | **固定 IP**，长期不变 |
| 凭证 | 服务端下发的 SS 密码，会轮换 | 匿名证书，**随取随用** |
| 计费/账号 | 商业白标，节点随时可能停发 | 公益设施，无计费无账号 |
| 端口 | 443 | 53 / 80 / 1194（53/80 多数受限网络可出） |
| 稳定性 | 6 台里 2 台 100% | 16 台里 11 台握手通过 |

**结论**：需要「长期不变的出口 IP」（账号绑定、IP 白名单、风控画像）用 Riseup；需要「大量轮换出口」用 EdgeVPN。

## 6. 运维要点

- **证书过期**：LEAP CA 五年期，但客户端证书建议按月重跑 `build_ovpn.py --fetch`。
- **`--dev null` 只能验证控制通道**：握手成功 ≠ 数据面通。真实建隧道后仍需用 `curl` 走 tun 里的 socks 端口确认出口 IP。
- **DNS**：Riseup 下推 `dhcp-option DNS 10.41.0.1`，`--route-nopull` 时 DNS 不会自动改；需要走隧道 DNS 就手动 `--dns` 或让 tun2socks 处理。
- **端口 53 是 DNS 端口**：某些网络会拦截非 DNS 载荷，用 tcp80 更稳。
