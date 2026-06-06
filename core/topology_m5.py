#!/usr/bin/env python3
"""
Campus network topology with two campuses (A and B), each with its own
802.1Q VLAN switch and dedicated trunk uplink to the core router.

Architecture: Dual-campus Router-on-a-Stick (双校区单臂路由)

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
  VLAN 10  - A-Dorm      10.0.10.0/24   gw c-eth0.10  10.0.10.254
  VLAN 20  - A-Teaching  10.0.20.0/24   gw c-eth0.20  10.0.20.254
  VLAN 30  - A-Library   10.0.30.0/24   gw c-eth0.30  10.0.30.254
  VLAN 40  - A-Office    10.0.40.0/24   gw c-eth0.40  10.0.40.254
  VLAN 50  - A-HR        10.0.50.0/24   gw c-eth0.50  10.0.50.254
  VLAN 60  - A-Finance   10.0.60.0/24   gw c-eth0.60  10.0.60.254
  VLAN 100 - Server      10.0.100.0/24  gw c-eth0.100 10.0.100.254
  VLAN 200 - VPN-In      10.0.200.0/24  gw c-eth0.200 10.0.200.254

Campus B (s2, uplink c-eth2):
  VLAN 10  - B-Dorm      10.1.10.0/24   gw c-eth2.10  10.1.10.254
  VLAN 20  - B-Teaching  10.1.20.0/24   gw c-eth2.20  10.1.20.254
  VLAN 30  - B-Library   10.1.30.0/24   gw c-eth2.30  10.1.30.254
  VLAN 40  - B-Office    10.1.40.0/24   gw c-eth2.40  10.1.40.254

Inter-campus ACL policy:
  - Both campuses can reach the shared server (VLAN 100)
  - A-Office and B-Office can reach A-HR and A-Finance
  - Dorm / Teaching / Library of either campus cannot reach HR or Finance
  - B-campus cannot reach A-HR / A-Finance directly
"""

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
# 这些 VLAN 走 trunk c-eth0
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
# 这些 VLAN 走 trunk c-eth2，与 A 校区相同的 VLAN ID 但网段不同
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
    "vpn":  ("s1", 200),   # vpn-eth0 接 s1 VLAN 200
    # ── Campus B ──────────────────────────────────────
    "bd1": ("s2", 10), "bd2": ("s2", 10),
    "bt1": ("s2", 20), "bt2": ("s2", 20),
    "bl1": ("s2", 30),
    "bo1": ("s2", 40), "bo2": ("s2", 40),
}


# ---------------------------------------------------------------------------
# 拓扑定义
# ---------------------------------------------------------------------------
class DualCampusVlanTopo(Topo):
    """
    双校区单臂路由拓扑。

    核心路由器 c 有三块网卡：
      c-eth0  trunk，连 A 校区交换机 s1
      c-eth1  普通链路，连互联网/VPN 交换机 is
      c-eth2  trunk，连 B 校区交换机 s2

    两个校区的 VLAN ID 可以重叠（如都有 VLAN 10），
    因为它们走不同的物理接口，子接口分别是 c-eth0.10 和 c-eth2.10，
    对应网段 10.0.10.0/24 和 10.1.10.0/24，互不干扰。
    """

    def build(self):
        # ── 核心路由器 ──────────────────────────────────────────────────────
        core = self.addHost("c", cls=LinuxRouter, ip=None)

        # ── 三个交换机 ──────────────────────────────────────────────────────
        s1  = self.addSwitch("s1",  dpid="0000000000000001")  # A 校区
        is_ = self.addSwitch("is",  dpid="0000000000000300")  # 互联网/VPN
        s2  = self.addSwitch("s2",  dpid="0000000000000002")  # B 校区

        # ── trunk 链路 ─────────────────────────────────────────────────────
        # addLink 的顺序决定路由器网卡编号：
        #   第 1 条 -> c-eth0（A 校区 trunk）
        #   第 2 条 -> c-eth1（互联网）
        #   第 3 条 -> c-eth2（B 校区 trunk）
        self.addLink(s1,  core)   # s1-eth1  <-> c-eth0
        self.addLink(is_, core)   # is-eth1  <-> c-eth1
        self.addLink(s2,  core)   # s2-eth1  <-> c-eth2

        # ================================================================
        # Campus A 主机
        # ================================================================

        # ── A 宿舍（VLAN 10）───────────────────────────────────────────────
        for i in range(1, 4):
            h = self.addHost(
                f"ad{i}",
                ip=f"10.0.10.{i}/24",
                mac=f"00:00:00:00:10:0{i}",
                defaultRoute="via 10.0.10.254",
            )
            self.addLink(h, s1)

        # ── A 教学楼（VLAN 20）─────────────────────────────────────────────
        for i in range(1, 3):
            h = self.addHost(
                f"at{i}",
                ip=f"10.0.20.{i}/24",
                mac=f"00:00:00:00:20:0{i}",
                defaultRoute="via 10.0.20.254",
            )
            self.addLink(h, s1)

        # ── A 图书馆（VLAN 30）─────────────────────────────────────────────
        h = self.addHost(
            "al1",
            ip="10.0.30.1/24",
            mac="00:00:00:00:30:01",
            defaultRoute="via 10.0.30.254",
        )
        self.addLink(h, s1)

        # ── A 办公楼（VLAN 40）─────────────────────────────────────────────
        for i in range(1, 3):
            h = self.addHost(
                f"ao{i}",
                ip=f"10.0.40.{i}/24",
                mac=f"00:00:00:00:40:0{i}",
                defaultRoute="via 10.0.40.254",
            )
            self.addLink(h, s1)

        # ── A 人事处（VLAN 50）─────────────────────────────────────────────
        for i in range(1, 3):
            h = self.addHost(
                f"ahr{i}",
                ip=f"10.0.50.{i}/24",
                mac=f"00:00:00:00:50:0{i}",
                defaultRoute="via 10.0.50.254",
            )
            self.addLink(h, s1)

        # ── A 财务处（VLAN 60）─────────────────────────────────────────────
        for i in range(1, 3):
            h = self.addHost(
                f"afn{i}",
                ip=f"10.0.60.{i}/24",
                mac=f"00:00:00:00:60:0{i}",
                defaultRoute="via 10.0.60.254",
            )
            self.addLink(h, s1)

        # ── 共享服务器区（VLAN 100，挂在 A 校区交换机）────────────────────
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

        # ── VPN 服务器（内网侧在 VLAN 200，公网侧在 is）───────────────────
        vpn = self.addHost("vpn", ip=None)
        self.addLink(vpn, s1)    # vpn-eth0 -> s1 VLAN 200
        self.addLink(vpn, is_)   # vpn-eth1 -> 公网侧

        # ── 外部客户端（模拟互联网）────────────────────────────────────────
        ex = self.addHost(
            "ex",
            ip="203.0.113.2/24",
            defaultRoute="via 203.0.113.1",
        )
        self.addLink(ex, is_)

        # ================================================================
        # Campus B 主机
        # ================================================================

        # ── B 宿舍（VLAN 10，网段 10.1.10.x）──────────────────────────────
        for i in range(1, 3):
            h = self.addHost(
                f"bd{i}",
                ip=f"10.1.10.{i}/24",
                mac=f"00:00:00:01:10:0{i}",
                defaultRoute="via 10.1.10.254",
            )
            self.addLink(h, s2)

        # ── B 教学楼（VLAN 20，网段 10.1.20.x）────────────────────────────
        for i in range(1, 3):
            h = self.addHost(
                f"bt{i}",
                ip=f"10.1.20.{i}/24",
                mac=f"00:00:00:01:20:0{i}",
                defaultRoute="via 10.1.20.254",
            )
            self.addLink(h, s2)

        # ── B 图书馆（VLAN 30，网段 10.1.30.x）────────────────────────────
        h = self.addHost(
            "bl1",
            ip="10.1.30.1/24",
            mac="00:00:00:01:30:01",
            defaultRoute="via 10.1.30.254",
        )
        self.addLink(h, s2)

        # ── B 办公楼（VLAN 40，网段 10.1.40.x）────────────────────────────
        for i in range(1, 3):
            h = self.addHost(
                f"bo{i}",
                ip=f"10.1.40.{i}/24",
                mac=f"00:00:00:01:40:0{i}",
                defaultRoute="via 10.1.40.254",
            )
            self.addLink(h, s2)


# ---------------------------------------------------------------------------
# 配置 OVS 交换机 + 手动打 VLAN access tag
# ---------------------------------------------------------------------------
def configure_switches(net):
    """
    将 s1、s2、is 设为 standalone 模式，
    并为每个 access 端口手动调用 ovs-vsctl set port ... tag=N。

    trunk 端口（s1-eth1 连 c，s2-eth1 连 c）不设 tag，保持 OVS 默认 trunk 行为。
    """
    info("*** Configuring OVS switches and VLAN access ports\n")

    for sw_name in ["s1", "s2", "is"]:
        sw = net.get(sw_name)
        sw.cmd(f"ovs-vsctl set-fail-mode {sw_name} standalone")
        sw.cmd(f"ovs-ofctl add-flow {sw_name} priority=0,actions=NORMAL")

    # 遍历所有主机，找到对应交换机上的端口，打上 access tag
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
# 配置 802.1Q 子接口
# ---------------------------------------------------------------------------
def configure_vlan_routing(net):
    """
    在路由器 c 上为两个校区分别创建 802.1Q 子接口。

    A 校区：c-eth0.10, c-eth0.20, ... （网段 10.0.x.x）
    B 校区：c-eth2.10, c-eth2.20, ... （网段 10.1.x.x）

    c-eth1 连互联网/VPN，不参与 VLAN。
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

    # ── 互联网/VPN 接口：c-eth1（不设 VLAN，直接激活）────────────────────
    core.cmd("ip addr flush dev c-eth1")
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

    # 验证
    result = core.cmd("ip -d link show type vlan 2>/dev/null | grep -E 'c-eth[02]\\.'")
    info("VLAN sub-interfaces:\n" + result + "\n")


# ---------------------------------------------------------------------------
# 配置 VPN 服务器地址
# ---------------------------------------------------------------------------
def configure_vpn_addresses(net):
    """vpn-eth0 在 VLAN 200（A 校区），vpn-eth1 在公网侧。"""
    info("*** Configuring VPN server addresses\n")

    vpn = net.get("vpn")
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
# 启动服务
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
# ACL 防火墙规则
# ---------------------------------------------------------------------------
def configure_acl(net):
    """
    校区间访问控制策略：

    共享服务器（10.0.100.x）：
      - 两个校区所有人都可以访问

    A 校区 HR（10.0.50.x）/ Finance（10.0.60.x）：
      - A-Office (10.0.40.x) 可以访问
      - B-Office (10.1.40.x) 可以访问（跨校区办公协作）
      - 其他网段一律拒绝

    校区内部：
      - 同校区各部门可以互相访问（除 HR/Finance 外）

    B 校区访问 A 校区普通部门：
      - 允许（模拟校区间普通互联）
    """
    info("*** Configuring ACL rules\n")

    core = net.get("c")
    ipt = core.cmd("command -v iptables").strip()
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
    # 允许：A-Office、B-Office
    core.cmd(f"{ipt} -A FORWARD -s 10.0.40.0/24 -d 10.0.50.0/24 -j ACCEPT")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.40.0/24 -d 10.0.50.0/24 -j ACCEPT")
    # 拒绝：其他所有来源
    core.cmd(f"{ipt} -A FORWARD -s 10.0.10.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.0.20.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.0.30.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.10.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.20.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.30.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD                 -d 10.0.50.0/24 -j DROP")

    # ── A-Finance（10.0.60.x）访问控制 ────────────────────────────────────
    # 允许：A-Office、B-Office
    core.cmd(f"{ipt} -A FORWARD -s 10.0.40.0/24 -d 10.0.60.0/24 -j ACCEPT")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.40.0/24 -d 10.0.60.0/24 -j ACCEPT")
    # 拒绝：其他所有来源
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
# Darkstat 监控
# ---------------------------------------------------------------------------
def start_darkstat(net):
    """在路由器 c 上启动 darkstat，同时监控两条 trunk 接口。"""
    info("*** Starting Darkstat traffic monitor\n")

    core = net.get("c")
    darkstat = core.cmd("command -v darkstat").strip()
    if not darkstat:
        info("!!! darkstat not found; install with: sudo apt install darkstat\n")
        return False

    log_path = "/tmp/mininet-m5-darkstat.log"
    pid_path = "/tmp/mininet-m5-darkstat.pid"

    core.cmd(
        f"if [ -f {pid_path} ]; then "
        f"  kill $(cat {pid_path}) 2>/dev/null || true; "
        f"  rm -f {pid_path}; fi"
    )
    core.cmd(f"rm -f {log_path}")

    # 监听 c-eth0（A 校区 trunk），也可改为 any 捕获所有接口
    core.cmd(
        f"{darkstat} -i any -b 0.0.0.0 -p 3001 --no-daemon "
        f"> {log_path} 2>&1 & echo $! > {pid_path}"
    )
    time.sleep(1)

    if "-p 3001" not in core.cmd("pgrep -a darkstat || true"):
        info(f"!!! darkstat failed; check: c cat {log_path}\n")
        return False

    info("darkstat monitoring c-eth0 (A-campus trunk)\n")
    info("Web UI: http://10.0.10.254:3001\n")
    info("Host browser access:\n")
    info("  sudo ip addr add 10.0.10.253/24 dev s1 2>/dev/null || true\n")
    info("  sudo ip link set s1 up\n")
    return True


# ---------------------------------------------------------------------------
# 连通性测试
# ---------------------------------------------------------------------------
def test_connectivity(net):
    """
    覆盖四类场景：
      1. 同校区同 VLAN 二层互通
      2. 同校区跨 VLAN 三层路由
      3. 跨校区三层路由（A <-> B）
      4. ACL 验证（HR/Finance 的访问控制）
    """
    info("*** Testing connectivity\n")

    ad1  = net.get("ad1")
    ao1  = net.get("ao1")
    bd1  = net.get("bd1")
    bo1  = net.get("bo1")
    ahr1 = net.get("ahr1")

    # ── 1. 网关连通性（验证 VLAN tag + 子接口是否正常）────────────────────
    r = ad1.cmd("ping -c 2 -W 2 10.0.10.254")
    info(f"[A VLAN10] ad1 -> gw c-eth0.10:           {'OK' if '0%' in r else 'FAIL'}\n")

    r = bd1.cmd("ping -c 2 -W 2 10.1.10.254")
    info(f"[B VLAN10] bd1 -> gw c-eth2.10:           {'OK' if '0%' in r else 'FAIL'}\n")

    # ── 2. 同校区跨 VLAN 路由 ──────────────────────────────────────────────
    r = ad1.cmd("ping -c 2 -W 2 10.0.20.1")
    info(f"[A 10->20] ad1 -> at1 (inter-VLAN):       {'OK' if '0%' in r else 'FAIL'}\n")

    r = bd1.cmd("ping -c 2 -W 2 10.1.20.1")
    info(f"[B 10->20] bd1 -> bt1 (inter-VLAN):       {'OK' if '0%' in r else 'FAIL'}\n")

    # ── 3. 跨校区路由（A <-> B）────────────────────────────────────────────
    r = ad1.cmd("ping -c 2 -W 2 10.1.10.1")
    info(f"[A->B] ad1 (10.0.10.1) -> bd1 (10.1.10.1):{'OK' if '0%' in r else 'FAIL'}\n")

    r = bd1.cmd("ping -c 2 -W 2 10.0.10.1")
    info(f"[B->A] bd1 (10.1.10.1) -> ad1 (10.0.10.1):{'OK' if '0%' in r else 'FAIL'}\n")

    # ── 4. 共享服务器（两个校区都能访问）──────────────────────────────────
    r = ad1.cmd("curl -s --connect-timeout 3 http://10.0.100.10")
    info(f"[A->Server] ad1 -> Web:                   {'OK' if 'Web Server' in r else 'FAIL'}\n")

    r = bd1.cmd("curl -s --connect-timeout 3 http://10.0.100.10")
    info(f"[B->Server] bd1 -> Web:                   {'OK' if 'Web Server' in r else 'FAIL'}\n")

    # ── 5. ACL：A 宿舍不能访问 A-HR ────────────────────────────────────────
    r = ad1.cmd("ping -c 2 -W 2 10.0.50.1")
    blocked = "100% packet loss" in r or "0 received" in r
    info(f"[ACL] ad1 (A-Dorm) -> ahr1 (A-HR):        {'BLOCKED (ok)' if blocked else 'ALLOWED (!)'}\n")

    # ── 6. ACL：B 宿舍不能访问 A-HR ────────────────────────────────────────
    r = bd1.cmd("ping -c 2 -W 2 10.0.50.1")
    blocked = "100% packet loss" in r or "0 received" in r
    info(f"[ACL] bd1 (B-Dorm) -> ahr1 (A-HR):        {'BLOCKED (ok)' if blocked else 'ALLOWED (!)'}\n")

    # ── 7. ACL：A 办公楼可以访问 A-HR ──────────────────────────────────────
    r = ao1.cmd("ping -c 2 -W 2 10.0.50.1")
    info(f"[ACL] ao1 (A-Office) -> ahr1 (A-HR):      {'OK' if '0%' in r else 'FAIL'}\n")

    # ── 8. ACL：B 办公楼可以访问 A-HR（跨校区协作）────────────────────────
    r = bo1.cmd("ping -c 2 -W 2 10.0.50.1")
    info(f"[ACL] bo1 (B-Office) -> ahr1 (A-HR):      {'OK' if '0%' in r else 'FAIL'}\n")

    # ── 9. ACL：A 宿舍不能访问 A-Finance ───────────────────────────────────
    r = ad1.cmd("ping -c 2 -W 2 10.0.60.1")
    blocked = "100% packet loss" in r or "0 received" in r
    info(f"[ACL] ad1 (A-Dorm) -> afn1 (A-Finance):   {'BLOCKED (ok)' if blocked else 'ALLOWED (!)'}\n")

    # ── 10. ACL：B 办公楼可以访问 A-Finance ────────────────────────────────
    r = bo1.cmd("ping -c 2 -W 2 10.0.60.1")
    info(f"[ACL] bo1 (B-Office) -> afn1 (A-Finance): {'OK' if '0%' in r else 'FAIL'}\n")


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------
def run():
    setLogLevel("info")

    info("*** Creating dual-campus VLAN topology (M5)\n")
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
        configure_switches(net)
        configure_vlan_routing(net)
        configure_vpn_addresses(net)
        start_services(net)
        configure_acl(net)
        start_darkstat(net)
        test_connectivity(net)

        info("\n*** Entering Mininet CLI\n")
        info("Network layout:\n")
        info("  Campus A (s1, 10.0.x.x):  ad1-ad3  at1-at2  al1  ao1-ao2  ahr1-ahr2  afn1-afn2\n")
        info("  Campus B (s2, 10.1.x.x):  bd1-bd2  bt1-bt2  bl1  bo1-bo2\n")
        info("  Shared server (VLAN 100): ws=10.0.100.10  fs=10.0.100.20\n")
        info("Useful commands:\n")
        info("  ad1 ping 10.1.10.1          # A->B cross-campus routing\n")
        info("  bd1 ping 10.0.10.1          # B->A cross-campus routing\n")
        info("  ad1 ping 10.0.50.1          # blocked by ACL\n")
        info("  bo1 ping 10.0.50.1          # allowed by ACL (B-Office -> A-HR)\n")
        info("  bd1 curl http://10.0.100.10 # B-campus access shared server\n")
        info("  c ip -d link show type vlan # show all VLAN sub-interfaces\n")
        info("  exit\n\n")

        CLI(net)

    except KeyboardInterrupt:
        info("\n*** Interrupted\n")
    finally:
        info("*** Stopping network\n")
        core = net.get("c")
        for vlan_id in CAMPUS_A_VLANS:
            core.cmd(f"ip link delete c-eth0.{vlan_id} 2>/dev/null || true")
        for vlan_id in CAMPUS_B_VLANS:
            core.cmd(f"ip link delete c-eth2.{vlan_id} 2>/dev/null || true")
        net.stop()


if __name__ == "__main__":
    run()
