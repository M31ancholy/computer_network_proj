#!/usr/bin/env python3
"""
Campus network topology with 802.1Q VLAN support.

Architecture: Router-on-a-Stick (单臂路由)
  - One core OVS switch (s1) handles all departments via VLAN tagging.
  - One trunk link connects s1 to the core router c.
  - Router c uses 802.1Q sub-interfaces (c-eth0.10, c-eth0.20, ...) as
    per-VLAN gateways.
  - External/VPN segment stays on a separate switch (is) to keep internet
    access clean and untangled from the VLAN trunk.

VLAN plan:
  VLAN 10  - Dorm     10.0.10.0/24   gw 10.0.10.254
  VLAN 20  - Teaching 10.0.20.0/24   gw 10.0.20.254
  VLAN 30  - Library  10.0.30.0/24   gw 10.0.30.254
  VLAN 40  - Office   10.0.40.0/24   gw 10.0.40.254
  VLAN 50  - HR       10.0.50.0/24   gw 10.0.50.254
  VLAN 60  - Finance  10.0.60.0/24   gw 10.0.60.254
  VLAN 100 - Server   10.0.100.0/24  gw 10.0.100.254
  VLAN 200 - VPN-In   10.0.200.0/24  gw 10.0.200.254
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
# VLAN 规划表：VLAN ID -> (网段描述, 网关IP/掩码, 主机IP前缀)
# ---------------------------------------------------------------------------
VLAN_TABLE = {
    10:  ("Dorm",     "10.0.10.254/24",  "10.0.10"),
    20:  ("Teaching", "10.0.20.254/24",  "10.0.20"),
    30:  ("Library",  "10.0.30.254/24",  "10.0.30"),
    40:  ("Office",   "10.0.40.254/24",  "10.0.40"),
    50:  ("HR",       "10.0.50.254/24",  "10.0.50"),
    60:  ("Finance",  "10.0.60.254/24",  "10.0.60"),
    100: ("Server",   "10.0.100.254/24", "10.0.100"),
    200: ("VPN-In",   "10.0.200.254/24", "10.0.200"),
}

# 主机名 -> VLAN ID 映射，供 configure_switches 使用
# （build() 里 addLink 的顺序决定了端口号，这里记录逻辑归属）
HOST_VLAN = {
    "d1": 10, "d2": 10, "d3": 10,
    "t1": 20, "t2": 20, "t3": 20,
    "l1": 30, "l2": 30,
    "o1": 40, "o2": 40,
    "hr1": 50, "hr2": 50,
    "fn1": 60, "fn2": 60,
    "ws": 100, "fs": 100,
    "vpn": 200,   # vpn-eth0 接 s1，归入 VLAN 200
}


# ---------------------------------------------------------------------------
# 拓扑定义
# ---------------------------------------------------------------------------
class CampusVlanTopo(Topo):
    """
    单臂路由 VLAN 拓扑。

    物理连线示意图：
                          ┌──────┐
        所有内部主机 ──── │  s1  │ ──── (trunk, c-eth0) ──── c (路由器)
                          └──────┘
        VPN/外部主机 ──── │  is  │ ──── (plain, c-eth1) ──── c
                          └──────┘

    s1 上每个主机端口打上对应 VLAN 的 access tag。
    c-eth0 与 s1 之间的链路为 trunk，允许所有 VLAN 帧通过。
    """

    def build(self):
        # ── 核心路由器 ──────────────────────────────────────────────────────
        core = self.addHost("c", cls=LinuxRouter, ip=None)

        # ── 核心 VLAN 交换机（单臂路由的"那根主干"连在这里）──────────────
        s1 = self.addSwitch("s1", dpid="0000000000000001")

        # ── 互联网/VPN 交换机（不参与 VLAN，保持独立）──────────────────────
        is_ = self.addSwitch("is", dpid="0000000000000300")

        # ── trunk 链路：s1 <-> c-eth0 ──────────────────────────────────────
        # OVS 默认端口为 trunk（允许所有 VLAN），此处不加 tag 参数
        self.addLink(s1, core)   # s1-eth1 <-> c-eth0

        # ── 互联网链路：is <-> c-eth1 ──────────────────────────────────────
        self.addLink(is_, core)  # is-eth1 <-> c-eth1

        # ── 宿舍区主机（VLAN 10）───────────────────────────────────────────
        for i in range(1, 4):
            h = self.addHost(
                f"d{i}",
                ip=f"10.0.10.{i}/24",
                mac=f"00:00:00:00:10:0{i}",
                defaultRoute="via 10.0.10.254",
            )
            # params1 针对主机侧端口，params2 针对交换机侧端口
            # 交换机侧端口打 VLAN 10 的 access tag
            self.addLink(h, s1, params2={"tag": 10})

        # ── 教学楼主机（VLAN 20）───────────────────────────────────────────
        for i in range(1, 4):
            h = self.addHost(
                f"t{i}",
                ip=f"10.0.20.{i}/24",
                mac=f"00:00:00:00:20:0{i}",
                defaultRoute="via 10.0.20.254",
            )
            self.addLink(h, s1, params2={"tag": 20})

        # ── 图书馆主机（VLAN 30）───────────────────────────────────────────
        for i in range(1, 3):
            h = self.addHost(
                f"l{i}",
                ip=f"10.0.30.{i}/24",
                mac=f"00:00:00:00:30:0{i}",
                defaultRoute="via 10.0.30.254",
            )
            self.addLink(h, s1, params2={"tag": 30})

        # ── 办公楼主机（VLAN 40）───────────────────────────────────────────
        for i in range(1, 3):
            h = self.addHost(
                f"o{i}",
                ip=f"10.0.40.{i}/24",
                mac=f"00:00:00:00:40:0{i}",
                defaultRoute="via 10.0.40.254",
            )
            self.addLink(h, s1, params2={"tag": 40})

        # ── 人事处主机（VLAN 50）───────────────────────────────────────────
        for i in range(1, 3):
            h = self.addHost(
                f"hr{i}",
                ip=f"10.0.50.{i}/24",
                mac=f"00:00:00:00:50:0{i}",
                defaultRoute="via 10.0.50.254",
            )
            self.addLink(h, s1, params2={"tag": 50})

        # ── 财务处主机（VLAN 60）───────────────────────────────────────────
        for i in range(1, 3):
            h = self.addHost(
                f"fn{i}",
                ip=f"10.0.60.{i}/24",
                mac=f"00:00:00:00:60:0{i}",
                defaultRoute="via 10.0.60.254",
            )
            self.addLink(h, s1, params2={"tag": 60})

        # ── 服务器区（VLAN 100）────────────────────────────────────────────
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
        self.addLink(ws, s1, params2={"tag": 100})
        self.addLink(fs, s1, params2={"tag": 100})

        # ── VPN 服务器（内网侧挂在 VLAN 200，公网侧挂在 is）────────────────
        vpn = self.addHost("vpn", ip=None)
        self.addLink(vpn, s1, params2={"tag": 200})   # vpn-eth0 -> VLAN 200
        self.addLink(vpn, is_)                         # vpn-eth1 -> 公网侧

        # ── 外部客户端（模拟互联网）────────────────────────────────────────
        ex = self.addHost(
            "ex",
            ip="203.0.113.2/24",
            defaultRoute="via 203.0.113.1",
        )
        self.addLink(ex, is_)


# ---------------------------------------------------------------------------
# 配置 OVS 交换机
# ---------------------------------------------------------------------------
def configure_switches(net):
    """
    配置 OVS 交换机的转发模式，并手动为每个 Access 端口打 VLAN tag。

    背景：Mininet 的 params2={"tag": N} 在部分 OVS 版本下不生效，
    因此这里在网络启动后通过 ovs-vsctl set port ... tag=N 显式配置。

    端口角色：
      s1-eth1        trunk 端口（连核心路由器 c，允许所有 VLAN 通过，不设 tag）
      s1-eth2 及以后  access 端口（各主机，设对应 VLAN 的 tag）
    """
    info("*** Configuring OVS switches and VLAN access ports\n")

    # 先设为 standalone 模式，让 OVS 自学习 MAC
    for name in ["s1", "is"]:
        sw = net.get(name)
        sw.cmd(f"ovs-vsctl set-fail-mode {name} standalone")
        sw.cmd(f"ovs-ofctl add-flow {name} priority=0,actions=NORMAL")

    s1 = net.get("s1")

    # 遍历所有主机，找到它们连在 s1 上的端口，然后手动设置 access tag
    for host_name, vlan_id in HOST_VLAN.items():
        host = net.get(host_name)
        # 找到该主机连接到 s1 的那块网卡
        for intf in host.intfList():
            link = intf.link
            if link is None:
                continue
            # link 的两端：intf1 <-> intf2，找到 s1 那一侧的端口名
            other = link.intf2 if link.intf1 == intf else link.intf1
            if other.node == s1:
                port_name = other.name   # 例如 s1-eth2
                s1.cmd(f"ovs-vsctl set port {port_name} tag={vlan_id}")
                info(f"  {port_name}  ->  {host_name:5s}  VLAN {vlan_id}\n")
                break

    # trunk 端口（s1-eth1，连路由器 c）不设 tag，保持默认 trunk 模式
    # OVS 上没有 tag 的端口默认就是 trunk，允许所有带标签的帧通过
    info("  s1-eth1  ->  c (trunk, all VLANs)\n")

    # 打印最终端口配置，方便验证
    info("\ns1 final port/VLAN config:\n")
    info(s1.cmd("ovs-vsctl show") + "\n")


# ---------------------------------------------------------------------------
# 配置 VLAN 子接口路由
# ---------------------------------------------------------------------------
def configure_vlan_routing(net):
    """
    在核心路由器 c 上配置 802.1Q 子接口，实现单臂路由。

    步骤：
      1. 加载 8021q 内核模块
      2. 激活物理 trunk 接口 c-eth0（不分配 IP，只做"主干"）
      3. 为每个 VLAN 创建虚拟子接口 c-eth0.<vlan_id>
      4. 为每个子接口分配网关 IP
    """
    info("*** Configuring 802.1Q VLAN sub-interfaces on router c\n")

    core = net.get("c")
    core.cmd("sysctl -w net.ipv4.ip_forward=1")

    # 加载 802.1Q 内核模块（在 Mininet 的 network namespace 里也需要）
    core.cmd("modprobe 8021q")

    # 激活 trunk 物理接口（不赋 IP）
    core.cmd("ip addr flush dev c-eth0")
    core.cmd("ip link set c-eth0 up")

    # 为每个 VLAN 创建子接口并设置网关
    for vlan_id, (name, gw_ip, _) in VLAN_TABLE.items():
        subif = f"c-eth0.{vlan_id}"
        core.cmd(f"ip link add link c-eth0 name {subif} type vlan id {vlan_id}")
        core.cmd(f"ip addr add {gw_ip} dev {subif}")
        core.cmd(f"ip link set {subif} up")
        info(f"  {subif:14s}  [{name:8s}]  gw {gw_ip}\n")

    # c-eth1 连接 VPN/互联网侧（不参与 VLAN，直接设 IP）
    core.cmd("ip addr flush dev c-eth1")
    core.cmd("ip link set c-eth1 up")

    # 验证子接口是否全部创建成功
    result = core.cmd("ip -d link show type vlan 2>/dev/null | grep 'c-eth0\\.'")
    info("VLAN sub-interfaces created:\n" + result + "\n")


# ---------------------------------------------------------------------------
# 配置 VPN 服务器的 IP
# ---------------------------------------------------------------------------
def configure_vpn_addresses(net):
    """
    给 VPN 服务器分配 IP 地址。
    vpn-eth0 在 VLAN 200 内，vpn-eth1 在公网侧（is 交换机）。
    """
    info("*** Configuring VPN server addresses\n")
    vpn = net.get("vpn")

    # 内网侧：VLAN 200
    vpn.cmd("ip addr flush dev vpn-eth0")
    vpn.cmd("ip addr add 10.0.200.10/24 dev vpn-eth0")
    vpn.cmd("ip link set vpn-eth0 up")
    vpn.cmd("ip route replace 10.0.0.0/16 via 10.0.200.254")

    # 公网侧：模拟互联网
    vpn.cmd("ip addr flush dev vpn-eth1")
    vpn.cmd("ip addr add 203.0.113.1/24 dev vpn-eth1")
    vpn.cmd("ip link set vpn-eth1 up")

    # 外部客户端
    ex = net.get("ex")
    ex.cmd("ip addr flush dev ex-eth0")
    ex.cmd("ip addr add 203.0.113.2/24 dev ex-eth0")
    ex.cmd("ip link set ex-eth0 up")
    ex.cmd("ip route replace default via 203.0.113.1")


# ---------------------------------------------------------------------------
# 配置 ACL 防火墙规则
# ---------------------------------------------------------------------------
def configure_acl(net):
    """
    在路由器 c 上使用 iptables 配置访问控制策略。

    规则逻辑（与 M2 保持一致）：
      - 所有人可访问服务器区的 Web(80) 和 FTP(21)
      - 办公楼 (VLAN 40) 可访问 HR (VLAN 50) 和 Finance (VLAN 60)
      - 其他区域禁止访问 HR / Finance
      - 已建立的连接允许回包（ESTABLISHED/RELATED）
    """
    info("*** Configuring ACL rules on router c\n")

    core = net.get("c")
    iptables = core.cmd("command -v iptables").strip()
    if not iptables:
        info("!!! iptables not found; skipping ACL\n")
        return

    # 清空已有规则
    core.cmd(f"{iptables} -F FORWARD")
    core.cmd(f"{iptables} -t nat -F")
    core.cmd(f"{iptables} -P FORWARD ACCEPT")

    # ── 服务器区开放规则 ────────────────────────────────────────────────────
    core.cmd(f"{iptables} -A FORWARD -d 10.0.100.10 -p tcp --dport 80  -j ACCEPT")
    core.cmd(f"{iptables} -A FORWARD -d 10.0.100.20 -p tcp --dport 21  -j ACCEPT")
    core.cmd(f"{iptables} -A FORWARD -d 10.0.100.0/24                  -j ACCEPT")

    # ── HR（VLAN 50）访问控制 ──────────────────────────────────────────────
    core.cmd(f"{iptables} -A FORWARD -s 10.0.40.0/24 -d 10.0.50.0/24  -j ACCEPT")  # 办公楼 -> HR 允许
    core.cmd(f"{iptables} -A FORWARD -s 10.0.10.0/24 -d 10.0.50.0/24  -j DROP")    # 宿舍 -> HR 拒绝
    core.cmd(f"{iptables} -A FORWARD -s 10.0.20.0/24 -d 10.0.50.0/24  -j DROP")    # 教学楼 -> HR 拒绝
    core.cmd(f"{iptables} -A FORWARD -s 10.0.30.0/24 -d 10.0.50.0/24  -j DROP")    # 图书馆 -> HR 拒绝
    core.cmd(f"{iptables} -A FORWARD                 -d 10.0.50.0/24  -j DROP")    # 其他 -> HR 兜底拒绝

    # ── Finance（VLAN 60）访问控制 ─────────────────────────────────────────
    core.cmd(f"{iptables} -A FORWARD -s 10.0.40.0/24 -d 10.0.60.0/24  -j ACCEPT")  # 办公楼 -> Finance 允许
    core.cmd(f"{iptables} -A FORWARD -s 10.0.10.0/24 -d 10.0.60.0/24  -j DROP")    # 宿舍 -> Finance 拒绝
    core.cmd(f"{iptables} -A FORWARD -s 10.0.20.0/24 -d 10.0.60.0/24  -j DROP")    # 教学楼 -> Finance 拒绝
    core.cmd(f"{iptables} -A FORWARD -s 10.0.30.0/24 -d 10.0.60.0/24  -j DROP")    # 图书馆 -> Finance 拒绝
    core.cmd(f"{iptables} -A FORWARD                 -d 10.0.60.0/24  -j DROP")    # 其他 -> Finance 兜底拒绝

    # ── 已建立连接允许回包 ─────────────────────────────────────────────────
    core.cmd(f"{iptables} -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT")

    info(core.cmd(f"{iptables} -vnL FORWARD --line-numbers"))


# ---------------------------------------------------------------------------
# 启动网络服务（Web / FTP）
# ---------------------------------------------------------------------------
def start_services(net):
    """在服务器区启动 HTTP 和 FTP 服务。"""
    info("*** Starting network services (Web + FTP)\n")

    ws = net.get("ws")
    ws.cmd("mkdir -p /var/www/html")
    ws.cmd('echo "<h1>Campus Web Server - VLAN 100</h1>" > /var/www/html/index.html')
    ws.cmd("python3 -m http.server 80 --directory /var/www/html &>/dev/null &")

    fs = net.get("fs")
    fs.cmd("mkdir -p /var/ftp")
    fs.cmd('echo "Welcome to Campus FTP" > /var/ftp/welcome.txt')
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
# 启动 Darkstat 流量监控
# ---------------------------------------------------------------------------
def start_darkstat(net):
    """
    在路由器 c 上启动 darkstat 监控所有 VLAN 流量。
    监听 c-eth0（trunk 接口），所有 VLAN 数据都会在这里经过。
    """
    info("*** Starting Darkstat traffic monitor on router c\n")

    core = net.get("c")
    darkstat = core.cmd("command -v darkstat").strip()
    log_path = "/tmp/mininet-m4-darkstat.log"
    pid_path = "/tmp/mininet-m4-darkstat.pid"

    if not darkstat:
        info("!!! darkstat not found; install with: sudo apt install darkstat\n")
        return False

    # 停掉旧进程
    core.cmd(
        f"if [ -f {pid_path} ]; then "
        f"  pid=$(cat {pid_path}); "
        f"  kill $pid 2>/dev/null || true; "
        f"  rm -f {pid_path}; "
        "fi"
    )
    core.cmd(f"rm -f {log_path}")

    # 监听 c-eth0（trunk）以捕获所有 VLAN 的流量
    core.cmd(
        f"{darkstat} -i c-eth0 -b 0.0.0.0 -p 3001 --no-daemon "
        f"> {log_path} 2>&1 & echo $! > {pid_path}"
    )
    time.sleep(1)

    if "-p 3001" not in core.cmd("pgrep -a darkstat || true"):
        info(f"!!! darkstat failed to start; check: c cat {log_path}\n")
        return False

    info("darkstat is monitoring trunk interface c-eth0 (all VLANs)\n")
    info("Web UI: http://10.0.10.254:3001\n")
    info("To access from host browser, run in another terminal:\n")
    info("  sudo ip addr add 10.0.10.253/24 dev s1 2>/dev/null || true\n")
    info("  sudo ip link set s1 up\n")
    return True


# ---------------------------------------------------------------------------
# 连通性测试
# ---------------------------------------------------------------------------
def test_connectivity(net):
    """
    验证 VLAN 间路由、ACL 规则和服务是否正常工作。

    关键验证逻辑：
      1. 同 VLAN 内二层互通（不经过路由器）
      2. 跨 VLAN 路由必须经过路由器 c 的子接口
      3. ACL 规则正确拦截 / 放行
    """
    info("*** Testing connectivity\n")

    d1  = net.get("d1")
    o1  = net.get("o1")
    hr1 = net.get("hr1")

    # ── 先 ping 网关，验证 VLAN tag 和子接口是否工作 ────────────────────────
    result = d1.cmd("ping -c 2 -W 2 10.0.10.254")
    info(f"[VLAN 10] d1 -> gateway (c-eth0.10):     "
         f"{'OK' if '0% packet loss' in result else 'FAIL'}\n")

    result = hr1.cmd("ping -c 2 -W 2 10.0.50.254")
    info(f"[VLAN 50] hr1 -> gateway (c-eth0.50):    "
         f"{'OK' if '0% packet loss' in result else 'FAIL'}\n")

    # ── 同 VLAN 内二层互通 ──────────────────────────────────────────────────
    result = d1.cmd("ping -c 2 -W 2 10.0.10.2")
    info(f"[VLAN 10] d1 -> d2 (same VLAN, L2):      "
         f"{'OK' if '0% packet loss' in result else 'FAIL'}\n")

    # ── 跨 VLAN 路由（必须经过路由器子接口）────────────────────────────────
    result = d1.cmd("ping -c 2 -W 2 10.0.20.1")
    info(f"[VLAN 10->20] d1 -> t1 (inter-VLAN L3):  "
         f"{'OK' if '0% packet loss' in result else 'FAIL'}\n")

    result = d1.cmd("ping -c 2 -W 2 10.0.30.1")
    info(f"[VLAN 10->30] d1 -> l1 (inter-VLAN L3):  "
         f"{'OK' if '0% packet loss' in result else 'FAIL'}\n")

    # ── 访问服务器区 Web 服务 ────────────────────────────────────────────────
    result = d1.cmd("curl -s --connect-timeout 3 http://10.0.100.10")
    info(f"[VLAN 10->100] d1 -> Web server:          "
         f"{'OK' if 'VLAN 100' in result else 'FAIL'}\n")

    # ── ACL 验证：宿舍不能访问 HR ───────────────────────────────────────────
    result = d1.cmd("ping -c 2 -W 2 10.0.50.1")
    blocked = "100% packet loss" in result or "0 received" in result
    info(f"[ACL] d1 (VLAN 10) -> hr1 (VLAN 50):     "
         f"{'BLOCKED (expected)' if blocked else 'ALLOWED (unexpected!)'}\n")

    # ── ACL 验证：宿舍不能访问 Finance ─────────────────────────────────────
    result = d1.cmd("ping -c 2 -W 2 10.0.60.1")
    blocked = "100% packet loss" in result or "0 received" in result
    info(f"[ACL] d1 (VLAN 10) -> fn1 (VLAN 60):     "
         f"{'BLOCKED (expected)' if blocked else 'ALLOWED (unexpected!)'}\n")

    # ── ACL 验证：办公楼可以访问 HR ────────────────────────────────────────
    result = o1.cmd("ping -c 2 -W 2 10.0.50.1")
    info(f"[ACL] o1 (VLAN 40) -> hr1 (VLAN 50):     "
         f"{'OK' if '0% packet loss' in result else 'FAIL'}\n")

    # ── ACL 验证：办公楼可以访问 Finance ───────────────────────────────────
    result = o1.cmd("ping -c 2 -W 2 10.0.60.1")
    info(f"[ACL] o1 (VLAN 40) -> fn1 (VLAN 60):     "
         f"{'OK' if '0% packet loss' in result else 'FAIL'}\n")

    # ── HR 内部同 VLAN 互通 ─────────────────────────────────────────────────
    result = hr1.cmd("ping -c 2 -W 2 10.0.50.2")
    info(f"[VLAN 50] hr1 -> hr2 (same VLAN, L2):    "
         f"{'OK' if '0% packet loss' in result else 'FAIL'}\n")


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------
def run():
    setLogLevel("info")

    info("*** Creating campus VLAN topology (M4 - Router-on-a-Stick)\n")
    topo = CampusVlanTopo()

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
        info("Useful commands:\n")
        info("  d1 ping t1                         # inter-VLAN routing\n")
        info("  d1 ping 10.0.50.1                  # should be blocked by ACL\n")
        info("  o1 ping 10.0.50.1                  # should be allowed\n")
        info("  d1 curl http://10.0.100.10         # web server\n")
        info("  c ip -d link show type vlan        # show VLAN sub-interfaces\n")
        info("  s1 ovs-vsctl show                  # show switch VLAN config\n")
        info("  exit\n\n")

        CLI(net)

    except KeyboardInterrupt:
        info("\n*** Interrupted\n")
    finally:
        info("*** Stopping network\n")
        # 清理子接口
        core = net.get("c")
        for vlan_id in VLAN_TABLE:
            core.cmd(f"ip link delete c-eth0.{vlan_id} 2>/dev/null || true")
        net.stop()


if __name__ == "__main__":
    run()
