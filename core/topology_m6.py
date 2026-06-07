#!/usr/bin/env python3
"""
Campus network topology - Milestone 6: DHCP + VPN
基于 M5 双校区单臂路由拓扑，新增 DHCP 动态 IP 分配功能 + 修复 VPN 回归。

架构：与 M5 相同的双校区单臂路由（Router-on-a-Stick）
新增：
  - 在核心路由器 c 的每个 VLAN 子接口上运行独立 dnsmasq 实例（纯 DHCP 模式）
  - 所有普通终端主机（宿舍/教学/图书馆/办公/人事/财务）通过 DHCP 自动获取 IP
  - 服务器区（ws, fs）和 VPN 节点（vpn, ex）保持静态 IP
修复（回归）：
  - vpn 启用 ip_forward，可在 vpn-eth0 / vpn-eth1 间转发
  - 启动 OpenVPN static-key 隧道（vpn <-> ex），外部客户端可经 VPN 访问内网
  - iptables MASQUERADE 让 VPN 客户端流量伪装为 vpn-eth0 IP
  - 核心路由器 c-eth1 分配 203.0.113.254/24，可参与公网侧通信

                ┌──────────────────────────────────────┐
                │           Core Router  c              │
                │  c-eth0 (trunk-A)                     │
                │  c-eth1 (internet/VPN)                │
                │  c-eth2 (trunk-B)                     │
                └────┬──────────────┬──────────────┬───┘
                     │              │              │
                 trunk-A        internet       trunk-B
                     │              │              │
                  ┌──┴──┐        ┌──┴──┐        ┌──┴──┐
                  │  s1  │        │  is  │        │  s2  │
                  └──┬──┘        └──┬──┘        └──┬──┘
               A-campus hosts   vpn/ex          B-campus hosts

Campus A (s1, uplink c-eth0):
  VLAN 10  - A-Dorm      10.0.10.0/24   gw 10.0.10.254  DHCP池 .50-.150
  VLAN 20  - A-Teaching  10.0.20.0/24   gw 10.0.20.254  DHCP池 .50-.150
  VLAN 30  - A-Library   10.0.30.0/24   gw 10.0.30.254  DHCP池 .50-.150
  VLAN 40  - A-Office    10.0.40.0/24   gw 10.0.40.254  DHCP池 .50-.150
  VLAN 50  - A-HR        10.0.50.0/24   gw 10.0.50.254  DHCP池 .50-.150
  VLAN 60  - A-Finance   10.0.60.0/24   gw 10.0.60.254  DHCP池 .50-.150
  VLAN 100 - Server      10.0.100.0/24  gw 10.0.100.254 静态（ws/fs）
  VLAN 200 - VPN-In      10.0.200.0/24  gw 10.0.200.254 静态（vpn）

Campus B (s2, uplink c-eth2):
  VLAN 10  - B-Dorm      10.1.10.0/24   gw 10.1.10.254  DHCP池 .50-.150
  VLAN 20  - B-Teaching  10.1.20.0/24   gw 10.1.20.254  DHCP池 .50-.150
  VLAN 30  - B-Library   10.1.30.0/24   gw 10.1.30.254  DHCP池 .50-.150
  VLAN 40  - B-Office    10.1.40.0/24   gw 10.1.40.254  DHCP池 .50-.150
"""

import re
import time

from mininet.cli import CLI
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import OVSController, OVSKernelSwitch
from mininet.topo import Topo
from mininet.util import dumpNodeConnections

from linux_router import LinuxRouter


# ---------------------------------------------------------------------------
# 规划表
# ---------------------------------------------------------------------------

# Campus A 的 VLAN 表：VLAN ID -> (描述, 网关IP/掩码)
CAMPUS_A_VLANS = {
    10:  ("A-Dorm",     "10.0.10.254/24"),
    20:  ("A-Teaching", "10.0.20.254/24"),
    30:  ("A-Library",  "10.0.30.254/24"),
    40:  ("A-Office",   "10.0.40.254/24"),
    50:  ("A-HR",       "10.0.50.254/24"),
    60:  ("A-Finance",  "10.0.60.254/24"),
    100: ("Server",     "10.0.100.254/24"),
    200: ("VPN-In",     "10.0.200.254/24"),
}

# Campus B 的 VLAN 表：VLAN ID -> (描述, 网关IP/掩码)
CAMPUS_B_VLANS = {
    10:  ("B-Dorm",     "10.1.10.254/24"),
    20:  ("B-Teaching", "10.1.20.254/24"),
    30:  ("B-Library",  "10.1.30.254/24"),
    40:  ("B-Office",   "10.1.40.254/24"),
}

# 主机名 -> (交换机名, VLAN ID) 映射，供 configure_switches 使用
HOST_SWITCH_VLAN = {
    # ── Campus A ──────────────────────────────────────
    "ad1": ("s1", 10), "ad2": ("s1", 10), "ad3": ("s1", 10),
    "at1": ("s1", 20), "at2": ("s1", 20),
    "al1": ("s1", 30),
    "ao1": ("s1", 40), "ao2": ("s1", 40),
    "ahr1": ("s1", 50), "ahr2": ("s1", 50),
    "afn1": ("s1", 60), "afn2": ("s1", 60),
    "ws":   ("s1", 100),
    "fs":   ("s1", 100),
    "vpn":  ("s1", 200),
    # ── Campus B ──────────────────────────────────────
    "bd1": ("s2", 10), "bd2": ("s2", 10),
    "bt1": ("s2", 20), "bt2": ("s2", 20),
    "bl1": ("s2", 30),
    "bo1": ("s2", 40), "bo2": ("s2", 40),
}

# ---------------------------------------------------------------------------
# M6 新增：DHCP 配置表
# ---------------------------------------------------------------------------

# 子接口名 -> (DHCP池起始IP, DHCP池结束IP, 网关IP, 租约时间)
# VLAN 100 (Server) 和 VLAN 200 (VPN-In) 不做 DHCP，服务器保持静态
DHCP_RANGES = {
    "c-eth0.10":  ("10.0.10.50",  "10.0.10.150",  "10.0.10.254",  "12h"),
    "c-eth0.20":  ("10.0.20.50",  "10.0.20.150",  "10.0.20.254",  "12h"),
    "c-eth0.30":  ("10.0.30.50",  "10.0.30.150",  "10.0.30.254",  "12h"),
    "c-eth0.40":  ("10.0.40.50",  "10.0.40.150",  "10.0.40.254",  "12h"),
    "c-eth0.50":  ("10.0.50.50",  "10.0.50.150",  "10.0.50.254",  "12h"),
    "c-eth0.60":  ("10.0.60.50",  "10.0.60.150",  "10.0.60.254",  "12h"),
    "c-eth2.10":  ("10.1.10.50",  "10.1.10.150",  "10.1.10.254",  "12h"),
    "c-eth2.20":  ("10.1.20.50",  "10.1.20.150",  "10.1.20.254",  "12h"),
    "c-eth2.30":  ("10.1.30.50",  "10.1.30.150",  "10.1.30.254",  "12h"),
    "c-eth2.40":  ("10.1.40.50",  "10.1.40.150",  "10.1.40.254",  "12h"),
}

# 通过 DHCP 动态获取 IP 的主机列表
# ws, fs（服务器），vpn, ex（VPN/公网）保持静态，不在此列
DHCP_HOSTS = [
    "ad1", "ad2", "ad3",          # A-Dorm
    "at1", "at2",                 # A-Teaching
    "al1",                        # A-Library
    "ao1", "ao2",                 # A-Office
    "ahr1", "ahr2",               # A-HR
    "afn1", "afn2",               # A-Finance
    "bd1", "bd2",                 # B-Dorm
    "bt1", "bt2",                 # B-Teaching
    "bl1",                        # B-Library
    "bo1", "bo2",                 # B-Office
]


# ---------------------------------------------------------------------------
# 拓扑定义
# ---------------------------------------------------------------------------
class DualCampusVlanTopo(Topo):
    """
    双校区单臂路由拓扑（M6：终端主机改为 DHCP 动态获取 IP）。

    核心路由器 c 有三块网卡：
      c-eth0  trunk，连 A 校区交换机 s1
      c-eth1  普通链路，连互联网/VPN 交换机 is
      c-eth2  trunk，连 B 校区交换机 s2

    DHCP 客户端主机在 addHost 时不配置 ip/defaultRoute，
    由后续 start_dhcp_servers() + configure_dhcp_clients() 动态分配。
    """

    def build(self):
        # ── 核心路由器 ──────────────────────────────────────────────────────
        core = self.addHost("c", cls=LinuxRouter, ip=None)

        # ── 三个交换机 ──────────────────────────────────────────────────────
        s1  = self.addSwitch("s1",  dpid="0000000000000001")  # A 校区
        is_ = self.addSwitch("is",  dpid="0000000000000300")  # 互联网/VPN
        s2  = self.addSwitch("s2",  dpid="0000000000000002")  # B 校区

        # ── trunk 链路（顺序决定路由器网卡编号）────────────────────────────
        self.addLink(s1,  core)   # s1-eth1  <-> c-eth0（A 校区 trunk）
        self.addLink(is_, core)   # is-eth1  <-> c-eth1（互联网/VPN）
        self.addLink(s2,  core)   # s2-eth1  <-> c-eth2（B 校区 trunk）

        # ================================================================
        # Campus A 主机
        # ================================================================

        # ── A 宿舍（VLAN 10）─── DHCP 客户端，不配静态 IP ────────────────
        for i in range(1, 4):
            h = self.addHost(
                f"ad{i}",
                ip="0.0.0.0",
                mac=f"00:00:00:00:10:0{i}",
            )
            self.addLink(h, s1)

        # ── A 教学楼（VLAN 20）─── DHCP 客户端 ───────────────────────────
        for i in range(1, 3):
            h = self.addHost(
                f"at{i}",
                ip="0.0.0.0",
                mac=f"00:00:00:00:20:0{i}",
            )
            self.addLink(h, s1)

        # ── A 图书馆（VLAN 30）─── DHCP 客户端 ───────────────────────────
        h = self.addHost(
            "al1",
            ip="0.0.0.0",
            mac="00:00:00:00:30:01",
        )
        self.addLink(h, s1)

        # ── A 办公楼（VLAN 40）─── DHCP 客户端 ───────────────────────────
        for i in range(1, 3):
            h = self.addHost(
                f"ao{i}",
                ip="0.0.0.0",
                mac=f"00:00:00:00:40:0{i}",
            )
            self.addLink(h, s1)

        # ── A 人事处（VLAN 50）─── DHCP 客户端 ───────────────────────────
        for i in range(1, 3):
            h = self.addHost(
                f"ahr{i}",
                ip="0.0.0.0",
                mac=f"00:00:00:00:50:0{i}",
            )
            self.addLink(h, s1)

        # ── A 财务处（VLAN 60）─── DHCP 客户端 ───────────────────────────
        for i in range(1, 3):
            h = self.addHost(
                f"afn{i}",
                ip="0.0.0.0",
                mac=f"00:00:00:00:60:0{i}",
            )
            self.addLink(h, s1)

        # ── 共享服务器区（VLAN 100）─── 保持静态 IP ───────────────────────
        ws = self.addHost(
            "ws",
            ip="10.0.100.10/24",
            mac="00:00:00:00:64:01",
            defaultRoute="via 10.0.100.254",
        )
        fs = self.addHost(
            "fs",
            ip="10.0.100.20/24",
            mac="00:00:00:00:64:02",
            defaultRoute="via 10.0.100.254",
        )
        self.addLink(ws, s1)
        self.addLink(fs, s1)

        # ── VPN 服务器（内网侧 VLAN 200，公网侧 is）─── 保持静态 ──────────
        vpn = self.addHost("vpn", ip=None)
        self.addLink(vpn, s1)    # vpn-eth0 -> s1 VLAN 200
        self.addLink(vpn, is_)   # vpn-eth1 -> 公网侧

        # ── 外部客户端（模拟互联网）─── 保持静态 ─────────────────────────
        ex = self.addHost(
            "ex",
            ip="203.0.113.2/24",
            defaultRoute="via 203.0.113.1",
        )
        self.addLink(ex, is_)

        # ================================================================
        # Campus B 主机
        # ================================================================

        # ── B 宿舍（VLAN 10，网段 10.1.10.x）─── DHCP 客户端 ─────────────
        for i in range(1, 3):
            h = self.addHost(
                f"bd{i}",
                ip="0.0.0.0",
                mac=f"00:00:00:01:10:0{i}",
            )
            self.addLink(h, s2)

        # ── B 教学楼（VLAN 20，网段 10.1.20.x）─── DHCP 客户端 ───────────
        for i in range(1, 3):
            h = self.addHost(
                f"bt{i}",
                ip="0.0.0.0",
                mac=f"00:00:00:01:20:0{i}",
            )
            self.addLink(h, s2)

        # ── B 图书馆（VLAN 30，网段 10.1.30.x）─── DHCP 客户端 ───────────
        h = self.addHost(
            "bl1",
            ip="0.0.0.0",
            mac="00:00:00:01:30:01",
        )
        self.addLink(h, s2)

        # ── B 办公楼（VLAN 40，网段 10.1.40.x）─── DHCP 客户端 ───────────
        for i in range(1, 3):
            h = self.addHost(
                f"bo{i}",
                ip="0.0.0.0",
                mac=f"00:00:00:01:40:0{i}",
            )
            self.addLink(h, s2)


# ---------------------------------------------------------------------------
# 配置 OVS 交换机 + 手动打 VLAN access tag（与 M5 相同）
# ---------------------------------------------------------------------------
def configure_switches(net):
    """
    将 s1、s2、is 设为 standalone 模式，
    并为每个 access 端口手动调用 ovs-vsctl set port ... tag=N。
    trunk 端口不设 tag，保持 OVS 默认 trunk 行为。
    """
    info("*** Configuring OVS switches and VLAN access ports\n")

    for sw_name in ["s1", "s2", "is"]:
        sw = net.get(sw_name)
        sw.cmd(f"ovs-vsctl set-fail-mode {sw_name} standalone")
        sw.cmd(f"ovs-ofctl add-flow {sw_name} priority=0,actions=NORMAL")

    for host_name, (sw_name, vlan_id) in HOST_SWITCH_VLAN.items():
        host = net.get(host_name)
        sw   = net.get(sw_name)
        for intf in host.intfList():
            link = intf.link
            if link is None:
                continue
            other = link.intf2 if link.intf1 == intf else link.intf1
            if other.node == sw:
                sw.cmd(f"ovs-vsctl set port {other.name} tag={vlan_id}")
                info(f"  {sw_name}:{other.name:10s} -> {host_name:6s}  VLAN {vlan_id}\n")
                break

    info("  s1-eth1 -> c-eth0 (trunk, A-campus all VLANs)\n")
    info("  s2-eth1 -> c-eth2 (trunk, B-campus all VLANs)\n")


# ---------------------------------------------------------------------------
# 配置 802.1Q 子接口（与 M5 相同）
# ---------------------------------------------------------------------------
def configure_vlan_routing(net):
    """
    在路由器 c 上为两个校区分别创建 802.1Q 子接口并分配网关 IP。
    A 校区：c-eth0.10, c-eth0.20, ...
    B 校区：c-eth2.10, c-eth2.20, ...
    """
    info("*** Configuring 802.1Q VLAN sub-interfaces on router c\n")

    core = net.get("c")
    core.cmd("sysctl -w net.ipv4.ip_forward=1")
    core.cmd("modprobe 8021q")

    # ── Campus A trunk：c-eth0 ─────────────────────────────────────────────
    info("  [Campus A] trunk interface: c-eth0\n")
    core.cmd("ip addr flush dev c-eth0")
    core.cmd("ip link set c-eth0 up")
    for vlan_id, (desc, gw_ip) in CAMPUS_A_VLANS.items():
        subif = f"c-eth0.{vlan_id}"
        core.cmd(f"ip link add link c-eth0 name {subif} type vlan id {vlan_id}")
        core.cmd(f"ip addr add {gw_ip} dev {subif}")
        core.cmd(f"ip link set {subif} up")
        info(f"    {subif:14s}  [{desc:12s}]  gw {gw_ip}\n")

    # ── 互联网/VPN 接口：c-eth1（不设 VLAN，分配公网侧 IP）────────────────────
    core.cmd("ip addr flush dev c-eth1")
    core.cmd("ip addr add 203.0.113.254/24 dev c-eth1")
    core.cmd("ip link set c-eth1 up")

    # ── Campus B trunk：c-eth2 ─────────────────────────────────────────────
    info("  [Campus B] trunk interface: c-eth2\n")
    core.cmd("ip addr flush dev c-eth2")
    core.cmd("ip link set c-eth2 up")
    for vlan_id, (desc, gw_ip) in CAMPUS_B_VLANS.items():
        subif = f"c-eth2.{vlan_id}"
        core.cmd(f"ip link add link c-eth2 name {subif} type vlan id {vlan_id}")
        core.cmd(f"ip addr add {gw_ip} dev {subif}")
        core.cmd(f"ip link set {subif} up")
        info(f"    {subif:14s}  [{desc:12s}]  gw {gw_ip}\n")

    result = core.cmd("ip -d link show type vlan 2>/dev/null | grep -E 'c-eth[02]\\.'")
    info("VLAN sub-interfaces:\n" + result + "\n")


# ---------------------------------------------------------------------------
# M6 新增：在路由器 c 上启动 DHCP 服务（每个 VLAN 子接口一个 dnsmasq 实例）
# ---------------------------------------------------------------------------
def start_dhcp_servers(net):
    """
    在核心路由器 c 的每个需要 DHCP 的 VLAN 子接口上独立启动一个 dnsmasq 进程。

    关键参数说明：
      --interface=<subif>      只监听该子接口，隔离各 VLAN
      --bind-interfaces        严格绑定，不跨接口响应
      --port=0                 禁用 DNS，专注纯 DHCP 模式
      --keep-in-foreground     【关键】不自行 daemonize/fork，由 bash 的 & 在
                               正确的 Mininet network namespace 内 fork，
                               避免进程逃逸到宿主机的全局 namespace
      --dhcp-range             地址池范围和租约时间
      --dhcp-option=3,<gw>     Option 3 = Default Router，告知客户端默认网关
      --dhcp-leasefile         租约持久化文件（/tmp 下，便于调试和清理）
      --log-facility=-         日志输出到 stderr（重定向到文件）
    """
    info("*** Starting DHCP servers (dnsmasq) on router c\n")

    core = net.get("c")

    # 清理上一次残留的 dnsmasq 进程和 lease 文件
    core.cmd("pkill -f 'keep-in-foreground' 2>/dev/null || true")
    core.cmd("rm -f /tmp/m6-dhcp-*.leases /tmp/m6-dhcp-*.pid /tmp/m6-dhcp-*.log")
    # 清除 dhcpcd 旧 lease（在 Python 层面删，因为是宿主机 fs）
    import glob as _glob
    for f in _glob.glob("/var/lib/dhcpcd/*.lease"):
        try:
            import os as _os
            _os.remove(f)
        except OSError:
            pass

    dnsmasq = core.cmd("command -v dnsmasq").strip()
    if not dnsmasq:
        info("!!! dnsmasq not found; install with: sudo apt install dnsmasq\n")
        return False

    for subif, (start, end, gw, lease) in DHCP_RANGES.items():
        # 将子接口名转换为合法文件名（如 c-eth0.10 -> c_eth0_10）
        safe = subif.replace("-", "_").replace(".", "_")
        lf   = f"/tmp/m6-dhcp-{safe}.leases"
        pf   = f"/tmp/m6-dhcp-{safe}.pid"    # 每实例独立 pid 文件，避免争抢 /var/run/dnsmasq.pid
        log  = f"/tmp/m6-dhcp-{safe}.log"

        # 用 --keep-in-foreground 阻止 dnsmasq 自行 daemonize，
        # 然后在 node 的 bash shell（已在正确 namespace）里用 & 后台化，
        # 这样所有子进程都留在 c 的 network namespace 内。
        # 注意：--pid-file 必须指定到 /tmp 下各自独立路径，
        # 否则多个实例争抢 /var/run/dnsmasq.pid 导致后启动的进程退出。
        cmd = (
            f"{dnsmasq}"
            f" --keep-in-foreground"
            f" --no-ping"
            f" --interface={subif}"
            f" --bind-interfaces"
            f" --port=0"
            f" --dhcp-range={start},{end},{lease}"
            f" --dhcp-option=3,{gw}"
            f" --dhcp-leasefile={lf}"
            f" --pid-file={pf}"
            f" --log-facility=-"
            f" > {log} 2>&1 &"
        )
        core.cmd(cmd)
        info(f"  dnsmasq on {subif:15s}  pool {start}-{end}  gw {gw}\n")

    # 等待 dnsmasq 完全绑定端口
    time.sleep(0.5)

    # 验证：在 c 的 namespace 内统计后台进程
    count = core.cmd("pgrep -c -f 'keep-in-foreground' 2>/dev/null || echo 0").strip()
    info(f"  {count} dnsmasq instance(s) running in router c namespace\n")
    return True


# ---------------------------------------------------------------------------
# M6 新增：在终端主机上启动 DHCP 客户端
# ---------------------------------------------------------------------------
def configure_dhcp_clients(net):
    """
    对 DHCP_HOSTS 中的每台主机：
      1. 清除 dhcpcd 残留的旧 lease 文件（/var/lib/dhcpcd/<intf>.lease）
         防止 dhcpcd 复用旧 lease 走 rebind→expire→IPv4LL 慢路径
      2. flush 掉 Mininet 自动配置的占位 IP
      3. 确保接口 UP
      4. 启动 dhcpcd

    关键：使用 -B (--nobackground) 阻止 dhcpcd 自行 daemonize，
    然后在 node 的 bash shell（已在正确的 Mininet network namespace 里）
    用 & 后台运行。这样 dhcpcd 的所有子进程都留在主机自己的 namespace，
    不会逃逸到宿主机的全局 namespace。

    等待策略：主动轮询每台主机是否拿到 IP，最多等 30 秒，
    避免硬编码 sleep 导致"等够了但还没拿到"或"早拿到但多等了"。
    """
    info("*** Starting DHCP clients on hosts\n")

    # 清除所有旧 lease，强制走全新 DISCOVER（避免 rebind 慢路径）
    for hname in DHCP_HOSTS:
        intf = f"{hname}-eth0"
        lease = f"/var/lib/dhcpcd/{intf}.lease"
        # 在宿主机层面删除（lease 文件在宿主机 fs，各 namespace 共享同一文件系统）
        import os
        try:
            os.remove(lease)
            info(f"  removed stale lease: {lease}\n")
        except FileNotFoundError:
            pass

    for hname in DHCP_HOSTS:
        h    = net.get(hname)
        intf = f"{hname}-eth0"
        h.cmd(f"ip addr flush dev {intf}")
        h.cmd(f"ip link set {intf} up")
        # -B: 不后台化（由 bash 的 & 在正确 namespace 内 fork）
        # -t 15: 最多等 15 秒获取租约
        # 日志重定向到文件，方便调试
        h.cmd(f"dhcpcd -B -t 15 {intf} > /tmp/m6-dhcpcd-{hname}.log 2>&1 &")
        info(f"  dhcpcd started on {hname} ({intf})\n")

    # 主动轮询：等到所有主机都拿到 IP，或超时 30 秒
    info("  Polling for DHCP leases (max 30s)...\n")
    deadline = time.time() + 30
    while time.time() < deadline:
        time.sleep(2)
        missing = []
        for hname in DHCP_HOSTS:
            h   = net.get(hname)
            out = h.cmd(f"ip -4 addr show dev {hname}-eth0 2>/dev/null")
            m   = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", out)
            if not m:
                missing.append(hname)
        if not missing:
            info("  All hosts obtained DHCP leases.\n")
            break
        info(f"  Still waiting: {', '.join(missing)}\n")
    else:
        info("  [WARN] Timeout: some hosts may not have obtained IP\n")

    # 打印每台主机获取到的 IP，便于肉眼验证
    info("*** DHCP lease summary\n")
    for hname in DHCP_HOSTS:
        h   = net.get(hname)
        out = h.cmd(f"ip -4 addr show dev {hname}-eth0 2>/dev/null")
        m   = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", out)
        ip  = m.group(1) if m else "NO IP"
        gw  = h.cmd("ip route show default 2>/dev/null").strip()
        info(f"  {hname:6s}  ip={ip:15s}  {gw}\n")


# ---------------------------------------------------------------------------
# 辅助函数：动态读取主机当前 IP（供测试函数使用）
# ---------------------------------------------------------------------------
def get_host_ip(node):
    """从主机的 eth0 接口读取当前 IPv4 地址，返回字符串，失败返回空串。"""
    intf = f"{node.name}-eth0"
    out  = node.cmd(f"ip -4 addr show dev {intf} 2>/dev/null")
    m    = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", out)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# 配置 VPN 服务器地址（与 M5 相同）
# ---------------------------------------------------------------------------
def configure_vpn_addresses(net):
    """vpn-eth0 在 VLAN 200（A 校区），vpn-eth1 在公网侧。启用 ip_forward。"""
    info("*** Configuring VPN server addresses\n")

    vpn = net.get("vpn")
    vpn.cmd("sysctl -w net.ipv4.ip_forward=1")
    vpn.cmd("ip addr flush dev vpn-eth0")
    vpn.cmd("ip addr add 10.0.200.10/24 dev vpn-eth0")
    vpn.cmd("ip link set vpn-eth0 up")
    vpn.cmd("ip route replace 10.0.0.0/8 via 10.0.200.254")

    vpn.cmd("ip addr flush dev vpn-eth1")
    vpn.cmd("ip addr add 203.0.113.1/24 dev vpn-eth1")
    vpn.cmd("ip link set vpn-eth1 up")

    ex = net.get("ex")
    ex.cmd("ip addr flush dev ex-eth0")
    ex.cmd("ip addr add 203.0.113.2/24 dev ex-eth0")
    ex.cmd("ip link set ex-eth0 up")
    ex.cmd("ip route replace default via 203.0.113.1")


# ---------------------------------------------------------------------------
# M6 新增：启动 OpenVPN 隧道（从 M2 回归修复）
# ---------------------------------------------------------------------------
def start_vpn_tunnel(net):
    """
    在 vpn（服务端）和 ex（客户端）之间建立 OpenVPN static-key 隧道。

    接口映射（与 M2 相反）：
      vpn-eth0 = VLAN 200 内网侧（10.0.200.10）
      vpn-eth1 = 公网侧（203.0.113.1）—— OpenVPN 监听此接口
      ex-eth0  = 公网侧（203.0.113.2）—— OpenVPN 客户端连此

    隧道地址：10.8.0.1（vpn tun0） <-> 10.8.0.2（ex tun0）
    iptables：VPN 客户端流量 MASQUERADE 到 vpn-eth0，使内网主机看到源为 10.0.200.10。
    """
    info("*** Starting VPN tunnel (OpenVPN)\n")

    vpn = net.get("vpn")
    ex  = net.get("ex")

    openvpn = vpn.cmd("command -v openvpn").strip()
    if not openvpn:
        info("!!! openvpn not found; install with: sudo apt install openvpn. Skipping tunnel.\n")
        return False

    iptables = vpn.cmd("command -v iptables").strip()
    if not iptables:
        info("!!! iptables not found on vpn; skipping VPN iptables rules.\n")
        iptables = ""

    vpn.cmd("pkill openvpn || true")
    ex.cmd("pkill openvpn || true")
    vpn.cmd("rm -f /tmp/mininet-vpn.key")
    vpn.cmd("openvpn --genkey --secret /tmp/mininet-vpn.key")

    server_config = (
        "port 1194\n"
        "proto udp\n"
        "dev tun0\n"
        "local 203.0.113.1\n"
        "ifconfig 10.8.0.1 10.8.0.2\n"
        "secret /tmp/mininet-vpn.key\n"
        "cipher AES-128-CBC\n"
        "keepalive 10 60\n"
        "persist-key\n"
        "persist-tun\n"
        "verb 3\n"
    )
    client_config = (
        "remote 203.0.113.1 1194\n"
        "proto udp\n"
        "dev tun0\n"
        "ifconfig 10.8.0.2 10.8.0.1\n"
        "secret /tmp/mininet-vpn.key\n"
        "cipher AES-128-CBC\n"
        "route 10.0.0.0 255.255.0.0\n"
        "nobind\n"
        "persist-key\n"
        "persist-tun\n"
        "verb 3\n"
    )

    vpn.cmd("rm -f /tmp/openvpn-server.conf /tmp/openvpn-server.log")
    ex.cmd("rm -f /tmp/openvpn-client.conf /tmp/openvpn-client.log")
    vpn.cmd(f"python3 -c \"from pathlib import Path; Path('/tmp/openvpn-server.conf').write_text({server_config!r})\"")
    ex.cmd(f"python3 -c \"from pathlib import Path; Path('/tmp/openvpn-client.conf').write_text({client_config!r})\"")
    key_data = vpn.cmd("python3 -c \"from pathlib import Path; print(Path('/tmp/mininet-vpn.key').read_text(), end='')\"")
    ex.cmd(f"python3 -c \"from pathlib import Path; Path('/tmp/mininet-vpn.key').write_text({key_data!r})\"")

    if iptables:
        vpn.cmd(f"{iptables} -F")
        vpn.cmd(f"{iptables} -t nat -F")
        vpn.cmd(f"{iptables} -P FORWARD ACCEPT")
        vpn.cmd(f"{iptables} -t nat -A POSTROUTING -s 10.8.0.0/24 -d 10.0.0.0/8 -o vpn-eth0 -j MASQUERADE")
        vpn.cmd(f"{iptables} -A FORWARD -i tun0 -o vpn-eth0 -s 10.8.0.0/24 -d 10.0.0.0/8 -j ACCEPT")
        vpn.cmd(f"{iptables} -A FORWARD -i vpn-eth0 -o tun0 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT")

    vpn.cmd("openvpn --config /tmp/openvpn-server.conf --daemon --log /tmp/openvpn-server.log")
    time.sleep(1)
    ex.cmd("openvpn --config /tmp/openvpn-client.conf --daemon --log /tmp/openvpn-client.log")
    time.sleep(3)

    tun_check = vpn.cmd("ip addr show tun0 2>/dev/null").strip()
    if "10.8.0.1" in tun_check:
        info("  VPN tunnel established: vpn tun0=10.8.0.1 <-> ex tun0=10.8.0.2\n")
    else:
        info("  [WARN] VPN tunnel may not be up; check logs:\n")
        info(f"    vpn: cat /tmp/openvpn-server.log\n")
        info(f"    ex:  cat /tmp/openvpn-client.log\n")

    return True


# ---------------------------------------------------------------------------
# 启动服务（与 M5 相同）
# ---------------------------------------------------------------------------
def start_services(net):
    """在共享服务器区启动 Web 和 FTP 服务。"""
    info("*** Starting network services (Web + FTP)\n")

    ws = net.get("ws")
    ws.cmd("mkdir -p /var/www/html")
    ws.cmd('echo "<h1>Shared Campus Web Server</h1>" > /var/www/html/index.html')
    ws.cmd("python3 -m http.server 80 --directory /var/www/html &>/dev/null &")

    fs = net.get("fs")
    fs.cmd("mkdir -p /var/ftp")
    fs.cmd('echo "Shared Campus FTP" > /var/ftp/welcome.txt')
    fs.cmd(
        'python3 -c "'
        "from pyftpdlib.authorizers import DummyAuthorizer; "
        "from pyftpdlib.handlers import FTPHandler; "
        "from pyftpdlib.servers import FTPServer; "
        'authorizer = DummyAuthorizer(); '
        'authorizer.add_anonymous("/var/ftp"); '
        "handler = FTPHandler; "
        "handler.authorizer = authorizer; "
        'server = FTPServer(("0.0.0.0", 21), handler); '
        'server.serve_forever()" &>/dev/null &'
    )


# ---------------------------------------------------------------------------
# ACL 防火墙规则（与 M5 相同）
# ---------------------------------------------------------------------------
def configure_acl(net):
    """
    校区间访问控制策略：
    - 共享服务器（10.0.100.x）：两个校区所有人都可以访问
    - A-HR（10.0.50.x）/ A-Finance（10.0.60.x）：
        允许 A-Office（10.0.40.x）和 B-Office（10.1.40.x）
        拒绝其他所有来源
    注：ACL 按网段控制，与 DHCP 动态分配的具体 IP 无关。
    """
    info("*** Configuring ACL rules\n")

    core = net.get("c")
    ipt  = core.cmd("command -v iptables").strip()
    if not ipt:
        info("!!! iptables not found; skipping ACL\n")
        return

    core.cmd(f"{ipt} -F FORWARD")
    core.cmd(f"{ipt} -t nat -F")
    core.cmd(f"{ipt} -P FORWARD ACCEPT")

    # ── 共享服务器区：所有人可以访问 ──────────────────────────────────────
    core.cmd(f"{ipt} -A FORWARD -d 10.0.100.10 -p tcp --dport 80 -j ACCEPT")
    core.cmd(f"{ipt} -A FORWARD -d 10.0.100.20 -p tcp --dport 21 -j ACCEPT")
    core.cmd(f"{ipt} -A FORWARD -d 10.0.100.0/24               -j ACCEPT")

    # ── A-HR（10.0.50.x）访问控制 ─────────────────────────────────────────
    core.cmd(f"{ipt} -A FORWARD -s 10.0.40.0/24 -d 10.0.50.0/24 -j ACCEPT")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.40.0/24 -d 10.0.50.0/24 -j ACCEPT")
    core.cmd(f"{ipt} -A FORWARD -s 10.0.10.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.0.20.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.0.30.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.10.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.20.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.30.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD                 -d 10.0.50.0/24 -j DROP")

    # ── A-Finance（10.0.60.x）访问控制 ────────────────────────────────────
    core.cmd(f"{ipt} -A FORWARD -s 10.0.40.0/24 -d 10.0.60.0/24 -j ACCEPT")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.40.0/24 -d 10.0.60.0/24 -j ACCEPT")
    core.cmd(f"{ipt} -A FORWARD -s 10.0.10.0/24 -d 10.0.60.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.0.20.0/24 -d 10.0.60.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.0.30.0/24 -d 10.0.60.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.10.0/24 -d 10.0.60.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.20.0/24 -d 10.0.60.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.30.0/24 -d 10.0.60.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD                 -d 10.0.60.0/24 -j DROP")

    # ── 已建立连接允许回包 ─────────────────────────────────────────────────
    core.cmd(f"{ipt} -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT")

    info(core.cmd(f"{ipt} -vnL FORWARD --line-numbers"))


# ---------------------------------------------------------------------------
# Darkstat 监控（与 M5 相同）
# ---------------------------------------------------------------------------
def start_darkstat(net):
    """在路由器 c 上启动 darkstat，监控两条 trunk 接口流量。"""
    info("*** Starting Darkstat traffic monitor\n")

    core    = net.get("c")
    darkstat = core.cmd("command -v darkstat").strip()
    if not darkstat:
        info("!!! darkstat not found; install with: sudo apt install darkstat\n")
        return False

    log_path = "/tmp/mininet-m6-darkstat.log"
    pid_path = "/tmp/mininet-m6-darkstat.pid"

    core.cmd(
        f"if [ -f {pid_path} ]; then "
        f"  kill $(cat {pid_path}) 2>/dev/null || true; "
        f"  rm -f {pid_path}; fi"
    )
    core.cmd(f"rm -f {log_path}")
    core.cmd(
        f"{darkstat} -i any -b 0.0.0.0 -p 3001 --no-daemon "
        f"> {log_path} 2>&1 & echo $! > {pid_path}"
    )
    time.sleep(1)

    if "-p 3001" not in core.cmd("pgrep -a darkstat || true"):
        info(f"!!! darkstat failed; check: c cat {log_path}\n")
        return False

    info("darkstat monitoring all interfaces on router c\n")
    info("Web UI: http://10.0.10.254:3001\n")
    return True


# ---------------------------------------------------------------------------
# 连通性测试（M6 改版：动态读取 DHCP 分配的 IP）
# ---------------------------------------------------------------------------
def test_connectivity(net):
    """
    覆盖五类场景：
      1. DHCP 获取验证（检查 IP 是否在预期池范围内）
      2. 同校区同 VLAN 二层互通
      3. 同校区跨 VLAN 三层路由
      4. 跨校区三层路由（A <-> B）
      5. ACL 验证（HR/Finance 的访问控制）

    所有目标 IP 均动态读取，不依赖硬编码地址。
    """
    info("*** Testing connectivity (M6 - DHCP-aware)\n")

    ad1  = net.get("ad1")
    ad2  = net.get("ad2")
    at1  = net.get("at1")
    ao1  = net.get("ao1")
    bd1  = net.get("bd1")
    bo1  = net.get("bo1")
    ahr1 = net.get("ahr1")
    afn1 = net.get("afn1")

    # 动态获取各主机的 IP
    ip_ad1  = get_host_ip(ad1)
    ip_ad2  = get_host_ip(ad2)
    ip_at1  = get_host_ip(at1)
    ip_ao1  = get_host_ip(ao1)
    ip_bd1  = get_host_ip(bd1)
    ip_bo1  = get_host_ip(bo1)
    ip_ahr1 = get_host_ip(ahr1)
    ip_afn1 = get_host_ip(afn1)

    info(f"  IP summary: ad1={ip_ad1}  at1={ip_at1}  ao1={ip_ao1}\n")
    info(f"              bd1={ip_bd1}  bo1={ip_bo1}\n")
    info(f"              ahr1={ip_ahr1}  afn1={ip_afn1}\n")

    # ── 1. DHCP 地址合法性验证 ─────────────────────────────────────────────
    def in_pool(ip, prefix):
        """检查 IP 是否在 .50-.150 的动态池内，prefix 如 '10.0.10.'"""
        if not ip.startswith(prefix):
            return False
        last = int(ip.split(".")[-1])
        return 50 <= last <= 150

    info("[DHCP] Validating assigned IPs are within pool range (.50-.150)\n")
    checks = [
        ("ad1",  ip_ad1,  "10.0.10."),
        ("at1",  ip_at1,  "10.0.20."),
        ("ao1",  ip_ao1,  "10.0.40."),
        ("ahr1", ip_ahr1, "10.0.50."),
        ("afn1", ip_afn1, "10.0.60."),
        ("bd1",  ip_bd1,  "10.1.10."),
        ("bo1",  ip_bo1,  "10.1.40."),
    ]
    for name, ip, prefix in checks:
        ok = in_pool(ip, prefix)
        info(f"  [DHCP] {name:5s}  ip={ip:15s}  {'PASS' if ok else 'FAIL (not in pool)'}\n")

    if not ip_ad1 or not ip_bd1:
        info("[WARN] Some hosts have no IP; skipping connectivity tests\n")
        return

    # ── 2. 网关连通性（VLAN tag + 子接口基础验证）────────────────────────
    r = ad1.cmd("ping -c 2 -W 2 10.0.10.254")
    info(f"[GW]   ad1 -> c-eth0.10 (10.0.10.254):   {'OK' if '0%' in r else 'FAIL'}\n")

    r = bd1.cmd("ping -c 2 -W 2 10.1.10.254")
    info(f"[GW]   bd1 -> c-eth2.10 (10.1.10.254):   {'OK' if '0%' in r else 'FAIL'}\n")

    # ── 3. 同校区同 VLAN 二层互通 ──────────────────────────────────────────
    if ip_ad2:
        r = ad1.cmd(f"ping -c 2 -W 2 {ip_ad2}")
        info(f"[L2]   ad1 -> ad2 ({ip_ad2}):  {'OK' if '0%' in r else 'FAIL'}\n")

    # ── 4. 同校区跨 VLAN 三层路由 ──────────────────────────────────────────
    if ip_at1:
        r = ad1.cmd(f"ping -c 2 -W 2 {ip_at1}")
        info(f"[L3-A] ad1 -> at1 ({ip_at1}):  {'OK' if '0%' in r else 'FAIL'}\n")

    # ── 5. 跨校区路由（A <-> B）────────────────────────────────────────────
    r = ad1.cmd(f"ping -c 2 -W 2 {ip_bd1}")
    info(f"[A->B] ad1 ({ip_ad1}) -> bd1 ({ip_bd1}): {'OK' if '0%' in r else 'FAIL'}\n")

    r = bd1.cmd(f"ping -c 2 -W 2 {ip_ad1}")
    info(f"[B->A] bd1 ({ip_bd1}) -> ad1 ({ip_ad1}): {'OK' if '0%' in r else 'FAIL'}\n")

    # ── 6. 共享服务器（两校区都能访问）────────────────────────────────────
    r = ad1.cmd("curl -s --connect-timeout 3 http://10.0.100.10")
    info(f"[SRV]  ad1 -> Web server:                 {'OK' if 'Web Server' in r else 'FAIL'}\n")

    r = bd1.cmd("curl -s --connect-timeout 3 http://10.0.100.10")
    info(f"[SRV]  bd1 -> Web server:                 {'OK' if 'Web Server' in r else 'FAIL'}\n")

    # ── 7. ACL：A 宿舍不能访问 A-HR ────────────────────────────────────────
    if ip_ahr1:
        r       = ad1.cmd(f"ping -c 2 -W 2 {ip_ahr1}")
        blocked = "100% packet loss" in r or "0 received" in r
        info(f"[ACL]  ad1 (A-Dorm) -> ahr1 ({ip_ahr1}):   {'BLOCKED (ok)' if blocked else 'ALLOWED (!)'}\n")

    # ── 8. ACL：A 办公楼可以访问 A-HR ──────────────────────────────────────
    if ip_ahr1:
        r = ao1.cmd(f"ping -c 2 -W 2 {ip_ahr1}")
        info(f"[ACL]  ao1 (A-Office) -> ahr1 ({ip_ahr1}): {'OK' if '0%' in r else 'FAIL'}\n")

    # ── 9. ACL：B 办公楼可以访问 A-HR（跨校区协作）────────────────────────
    if ip_ahr1:
        r = bo1.cmd(f"ping -c 2 -W 2 {ip_ahr1}")
        info(f"[ACL]  bo1 (B-Office) -> ahr1 ({ip_ahr1}): {'OK' if '0%' in r else 'FAIL'}\n")

    # ── 10. ACL：A 宿舍不能访问 A-Finance ──────────────────────────────────
    if ip_afn1:
        r       = ad1.cmd(f"ping -c 2 -W 2 {ip_afn1}")
        blocked = "100% packet loss" in r or "0 received" in r
        info(f"[ACL]  ad1 (A-Dorm) -> afn1 ({ip_afn1}): {'BLOCKED (ok)' if blocked else 'ALLOWED (!)'}\n")

    # ── 11. ACL：B 办公楼可以访问 A-Finance ────────────────────────────────
    if ip_afn1:
        r = bo1.cmd(f"ping -c 2 -W 2 {ip_afn1}")
        info(f"[ACL]  bo1 (B-Office) -> afn1 ({ip_afn1}): {'OK' if '0%' in r else 'FAIL'}\n")

    # ── 12. VPN 连通性 ───────────────────────────────────────────────────────
    vpn = net.get("vpn")
    ex  = net.get("ex")

    r = ad1.cmd("ping -c 2 -W 2 10.0.200.10")
    info(f"[VPN]  ad1 -> vpn-eth0 (10.0.200.10):  {'OK' if '0%' in r else 'FAIL'}\n")

    r = ex.cmd("ping -c 2 -W 2 203.0.113.1")
    info(f"[VPN]  ex -> vpn-eth1 (203.0.113.1):   {'OK' if '0%' in r else 'FAIL'}\n")

    r = vpn.cmd("ping -c 2 -W 2 203.0.113.2")
    info(f"[VPN]  vpn -> ex (203.0.113.2):        {'OK' if '0%' in r else 'FAIL'}\n")

    tun0_out = vpn.cmd("ip addr show tun0 2>/dev/null").strip()
    if "10.8.0.1" in tun0_out:
        r = ex.cmd("ping -c 2 -W 2 10.8.0.1")
        info(f"[VPN]  ex -> vpn tunnel (10.8.0.1): {'OK' if '0%' in r else 'FAIL'}\n")

        r = ex.cmd("curl -s --connect-timeout 3 http://10.0.100.10")
        info(f"[VPN]  ex via VPN -> Web server:     {'OK' if 'Web Server' in r else 'FAIL'}\n")

        r = ex.cmd("curl -s --connect-timeout 3 ftp://10.0.100.20/welcome.txt")
        info(f"[VPN]  ex via VPN -> FTP welcome:    {'OK' if 'Shared Campus FTP' in r else 'FAIL'}\n")
    else:
        info("[VPN]  Tunnel not up; skipping VPN-through-tunnel tests\n")


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------
def run():
    setLogLevel("info")

    info("*** Creating dual-campus VLAN topology with DHCP (M6)\n")
    topo = DualCampusVlanTopo()

    net = Mininet(
        topo=topo,
        controller=OVSController,
        switch=OVSKernelSwitch,
        autoSetMacs=True,
        autoStaticArp=False,
    )

    info("*** Starting network\n")
    net.start()
    dumpNodeConnections(net.hosts)

    try:
        # 1. 配置 OVS 交换机 VLAN 标签（同 M5）
        configure_switches(net)

        # 2. 创建 802.1Q 子接口并分配网关 IP（同 M5）
        configure_vlan_routing(net)

        # 3. 【M6 新增】在路由器 c 上为每个 VLAN 子接口启动 dnsmasq DHCP 服务
        start_dhcp_servers(net)

        # 4. 配置 VPN 和外部客户端静态地址（修复 ip_forward）
        configure_vpn_addresses(net)

        # 5. 【M6 修复】启动 OpenVPN 隧道
        vpn_up = start_vpn_tunnel(net)

        # 6. 【M6 新增】在终端主机上启动 dhcpcd，等待动态 IP 分配完成
        configure_dhcp_clients(net)

        # 7. 启动 Web/FTP 服务（同 M5）
        start_services(net)

        # 8. 配置 iptables ACL（同 M5，按网段规则，与动态 IP 无关）
        configure_acl(net)

        # 9. 启动 Darkstat 流量监控（同 M5）
        start_darkstat(net)

        # 10. 连通性测试（M6 改版：动态读 IP + VPN 测试）
        test_connectivity(net)

        info("\n*** Entering Mininet CLI (M6 - DHCP + VPN enabled)\n")
        info("Network layout:\n")
        info("  Campus A (s1, 10.0.x.x):  ad1-ad3  at1-at2  al1  ao1-ao2  ahr1-ahr2  afn1-afn2  [DHCP]\n")
        info("  Campus B (s2, 10.1.x.x):  bd1-bd2  bt1-bt2  bl1  bo1-bo2              [DHCP]\n")
        info("  Static:  ws=10.0.100.10  fs=10.0.100.20  vpn=10.0.200.10/203.0.113.1\n")
        info("DHCP pool range: .50 - .150 per VLAN subnet\n")
        info("Useful commands:\n")
        info("  ad1 ip addr              # show DHCP-assigned IP\n")
        info("  ad1 ip route             # show default route from DHCP\n")
        info("  c cat /tmp/m6-dhcp-c_eth0_10.leases  # view DHCP leases for A-Dorm\n")
        info("  ad1 ping 10.1.10.254     # A->B gateway\n")
        info("  ad1 ping <bd1-ip>        # A->B cross-campus (get ip via: bd1 ip addr)\n")
        info("  bd1 curl http://10.0.100.10  # B-campus access shared Web server\n")
        info("  ad1 curl ftp://10.0.100.20/welcome.txt  # A-campus access shared FTP\n")
        info("  c iptables -vnL FORWARD --line-numbers  # view ACL rules\n")
        info("  VPN demo:\n")
        info("    ex ping 203.0.113.1          # external -> VPN public IP\n")
        info("    ex ping 10.8.0.1             # external -> VPN tunnel endpoint\n")
        info("    ex curl http://10.0.100.10    # external via VPN -> internal Web\n")
        info("    vpn iptables -vnL FORWARD     # VPN NAT/forward rules\n")
        info("    vpn cat /tmp/openvpn-server.log  # VPN tunnel status\n")
        info("  exit\n\n")

        CLI(net)

    except KeyboardInterrupt:
        info("\n*** Interrupted\n")
    finally:
        info("*** Stopping network and cleaning up\n")
        core = net.get("c")

        # 停止所有 DHCP 客户端（在各自的 namespace 内 kill dhcpcd）
        for hname in DHCP_HOSTS:
            try:
                net.get(hname).cmd("pkill -f dhcpcd 2>/dev/null || true")
            except Exception:
                pass

        # 停止路由器 c 上所有 dnsmasq 实例（按 pid 文件 kill，再按特征 pkill 兜底）
        for subif in DHCP_RANGES:
            safe = subif.replace("-", "_").replace(".", "_")
            pf   = f"/tmp/m6-dhcp-{safe}.pid"
            core.cmd(f"[ -f {pf} ] && kill $(cat {pf}) 2>/dev/null || true; rm -f {pf}")
        core.cmd("pkill -f 'keep-in-foreground' 2>/dev/null || true")
        core.cmd("rm -f /tmp/m6-dhcp-*.leases /tmp/m6-dhcp-*.log /tmp/m6-dhcpcd-*.log")

        # 停止 darkstat
        core.cmd(
            "if [ -f /tmp/mininet-m6-darkstat.pid ]; then "
            "  kill $(cat /tmp/mininet-m6-darkstat.pid) 2>/dev/null || true; "
            "  rm -f /tmp/mininet-m6-darkstat.pid; fi"
        )

        # 停止 VPN 隧道（vpn 和 ex 上的 openvpn 进程）
        try:
            vpn = net.get("vpn")
            ex  = net.get("ex")
            vpn.cmd("pkill openvpn 2>/dev/null || true")
            ex.cmd("pkill openvpn 2>/dev/null || true")
            vpn.cmd("rm -f /tmp/mininet-vpn.key /tmp/openvpn-server.conf /tmp/openvpn-server.log")
            ex.cmd("rm -f /tmp/mininet-vpn.key /tmp/openvpn-client.conf /tmp/openvpn-client.log")
        except Exception:
            pass

        # 删除 VLAN 子接口
        for vlan_id in CAMPUS_A_VLANS:
            core.cmd(f"ip link delete c-eth0.{vlan_id} 2>/dev/null || true")
        for vlan_id in CAMPUS_B_VLANS:
            core.cmd(f"ip link delete c-eth2.{vlan_id} 2>/dev/null || true")

        net.stop()


if __name__ == "__main__":
    run()
