#!/usr/bin/env python3
"""
Campus network topology with DHCP support (extends M5).

Same dual-campus architecture as topology_m5.py, but all campus hosts
obtain their IP addresses via DHCP (dnsmasq on router c) with static
MAC-IP bindings, so every host always gets the same IP as before.

Architecture: Dual-campus Router-on-a-Stick (双校区单臂路由)
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

CAMPUS_B_VLANS = {
    10:  ("B-Dorm",     "10.1.10.254/24"),
    20:  ("B-Teaching", "10.1.20.254/24"),
    30:  ("B-Library",  "10.1.30.254/24"),
    40:  ("B-Office",   "10.1.40.254/24"),
}

HOST_SWITCH_VLAN = {
    "ad1": ("s1", 10), "ad2": ("s1", 10), "ad3": ("s1", 10),
    "at1": ("s1", 20), "at2": ("s1", 20),
    "al1": ("s1", 30),
    "ao1": ("s1", 40), "ao2": ("s1", 40),
    "ahr1": ("s1", 50), "ahr2": ("s1", 50),
    "afn1": ("s1", 60), "afn2": ("s1", 60),
    "ws":   ("s1", 100),
    "fs":   ("s1", 100),
    "vpn":  ("s1", 200),
    "bd1": ("s2", 10), "bd2": ("s2", 10),
    "bt1": ("s2", 20), "bt2": ("s2", 20),
    "bl1": ("s2", 30),
    "bo1": ("s2", 40), "bo2": ("s2", 40),
}

# DHCP 静态租约：主机名 -> (IP, MAC)
# 每个 campus 主机通过 MAC 绑定获取固定 IP，和 m5 完全一致
DHCP_LEASE = {
    "ad1":  ("10.0.10.1",   "00:00:00:00:10:01"),
    "ad2":  ("10.0.10.2",   "00:00:00:00:10:02"),
    "ad3":  ("10.0.10.3",   "00:00:00:00:10:03"),
    "at1":  ("10.0.20.1",   "00:00:00:00:20:01"),
    "at2":  ("10.0.20.2",   "00:00:00:00:20:02"),
    "al1":  ("10.0.30.1",   "00:00:00:00:30:01"),
    "ao1":  ("10.0.40.1",   "00:00:00:00:40:01"),
    "ao2":  ("10.0.40.2",   "00:00:00:00:40:02"),
    "ahr1": ("10.0.50.1",   "00:00:00:00:50:01"),
    "ahr2": ("10.0.50.2",   "00:00:00:00:50:02"),
    "afn1": ("10.0.60.1",   "00:00:00:00:60:01"),
    "afn2": ("10.0.60.2",   "00:00:00:00:60:02"),
    "bd1":  ("10.1.10.1",   "00:00:00:01:10:01"),
    "bd2":  ("10.1.10.2",   "00:00:00:01:10:02"),
    "bt1":  ("10.1.20.1",   "00:00:00:01:20:01"),
    "bt2":  ("10.1.20.2",   "00:00:00:01:20:02"),
    "bl1":  ("10.1.30.1",   "00:00:00:01:30:01"),
    "bo1":  ("10.1.40.1",   "00:00:00:01:40:01"),
    "bo2":  ("10.1.40.2",   "00:00:00:01:40:02"),
}


# ---------------------------------------------------------------------------
# 拓扑定义
# ---------------------------------------------------------------------------
class DualCampusVlanTopo(Topo):
    """
    双校区单臂路由拓扑 — DHCP 版本。

    与 M5 的拓扑一致，但普通主机不设静态 IP，
    IP 交由核心路由器 c 上的 dnsmasq 分配。
    """

    def build(self):
        core = self.addHost("c", cls=LinuxRouter, ip=None)

        s1  = self.addSwitch("s1",  dpid="0000000000000001")
        is_ = self.addSwitch("is",  dpid="0000000000000300")
        s2  = self.addSwitch("s2",  dpid="0000000000000002")

        self.addLink(s1,  core)
        self.addLink(is_, core)
        self.addLink(s2,  core)

        # ── Campus A 主机（无静态 IP，走 DHCP）────────────────────────────

        for i in range(1, 4):
            h = self.addHost(
                f"ad{i}",
                mac=f"00:00:00:00:10:0{i}",
            )
            self.addLink(h, s1)

        for i in range(1, 3):
            h = self.addHost(
                f"at{i}",
                mac=f"00:00:00:00:20:0{i}",
            )
            self.addLink(h, s1)

        h = self.addHost("al1", mac="00:00:00:00:30:01")
        self.addLink(h, s1)

        for i in range(1, 3):
            h = self.addHost(
                f"ao{i}",
                mac=f"00:00:00:00:40:0{i}",
            )
            self.addLink(h, s1)

        for i in range(1, 3):
            h = self.addHost(
                f"ahr{i}",
                mac=f"00:00:00:00:50:0{i}",
            )
            self.addLink(h, s1)

        for i in range(1, 3):
            h = self.addHost(
                f"afn{i}",
                mac=f"00:00:00:00:60:0{i}",
            )
            self.addLink(h, s1)

        # ── 共享服务器区（静态 IP，不参与 DHCP）───────────────────────────
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

        # ── VPN 服务器 ──────────────────────────────────────────────────────
        vpn = self.addHost("vpn", ip=None)
        self.addLink(vpn, s1)
        self.addLink(vpn, is_)

        # ── 外部客户端 ──────────────────────────────────────────────────────
        ex = self.addHost(
            "ex",
            ip="203.0.113.2/24",
            defaultRoute="via 203.0.113.1",
        )
        self.addLink(ex, is_)

        # ── Campus B 主机（无静态 IP，走 DHCP）────────────────────────────

        for i in range(1, 3):
            h = self.addHost(
                f"bd{i}",
                mac=f"00:00:00:01:10:0{i}",
            )
            self.addLink(h, s2)

        for i in range(1, 3):
            h = self.addHost(
                f"bt{i}",
                mac=f"00:00:00:01:20:0{i}",
            )
            self.addLink(h, s2)

        h = self.addHost("bl1", mac="00:00:00:01:30:01")
        self.addLink(h, s2)

        for i in range(1, 3):
            h = self.addHost(
                f"bo{i}",
                mac=f"00:00:00:01:40:0{i}",
            )
            self.addLink(h, s2)


# ---------------------------------------------------------------------------
# 配置 OVS 交换机
# ---------------------------------------------------------------------------
def configure_switches(net):
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
# 配置 802.1Q 子接口
# ---------------------------------------------------------------------------
def configure_vlan_routing(net):
    info("*** Configuring 802.1Q VLAN sub-interfaces on router c\n")

    core = net.get("c")
    core.cmd("sysctl -w net.ipv4.ip_forward=1")
    core.cmd("modprobe 8021q")

    info("  [Campus A] trunk interface: c-eth0\n")
    core.cmd("ip addr flush dev c-eth0")
    core.cmd("ip link set c-eth0 up")
    for vlan_id, (desc, gw_ip) in CAMPUS_A_VLANS.items():
        subif = f"c-eth0.{vlan_id}"
        core.cmd(f"ip link add link c-eth0 name {subif} type vlan id {vlan_id}")
        core.cmd(f"ip addr add {gw_ip} dev {subif}")
        core.cmd(f"ip link set {subif} up")
        info(f"    {subif:14s}  [{desc:12s}]  gw {gw_ip}\n")

    core.cmd("ip addr flush dev c-eth1")
    core.cmd("ip link set c-eth1 up")

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
# DHCP 服务器（dnsmasq）
# ---------------------------------------------------------------------------
def configure_dhcp(net):
    info("*** Configuring DHCP server (dnsmasq) on router c\n")

    core = net.get("c")
    dnsmasq = core.cmd("command -v dnsmasq").strip()
    if not dnsmasq:
        info("!!! dnsmasq not found; install with: sudo apt install dnsmasq\n")
        return

    core.cmd("pkill -f 'dnsmasq.*mininet-m6' 2>/dev/null || true")

    conf_path = "/tmp/mininet-m6-dhcp.conf"
    pid_path  = "/tmp/mininet-m6-dhcp.pid"
    log_path  = "/tmp/mininet-m6-dhcp.log"

    lines = [
        "port=0",
        "dhcp-authoritative",
        "log-dhcp",
    ]

    for vlan_id, (_desc, gw_ip) in CAMPUS_A_VLANS.items():
        gw = gw_ip.split("/")[0]
        net_addr = gw.rsplit(".", 1)[0] + ".0"
        lines.append(f"dhcp-range={net_addr},static,255.255.255.0,1h")
        lines.append(f"dhcp-option=3,{gw}")

    for vlan_id, (_desc, gw_ip) in CAMPUS_B_VLANS.items():
        gw = gw_ip.split("/")[0]
        net_addr = gw.rsplit(".", 1)[0] + ".0"
        lines.append(f"dhcp-range={net_addr},static,255.255.255.0,1h")
        lines.append(f"dhcp-option=3,{gw}")

    for hostname, (ip, mac) in DHCP_LEASE.items():
        lines.append(f"dhcp-host={mac},{ip}")

    with open(conf_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    core.cmd(f"rm -f {pid_path} {log_path}")
    core.cmd(
        f"{dnsmasq} -C {conf_path} -x {pid_path} "
        f"--no-daemon > {log_path} 2>&1 &"
    )
    time.sleep(1)

    if core.cmd(f"pgrep -f 'dnsmasq.*{pid_path}' || true").strip():
        info("*** DHCP server started successfully\n")
    else:
        info("!!! DHCP server failed; check: c cat {log_path}\n")
        info(core.cmd(f"cat {log_path}"))
        return

    for hostname in DHCP_LEASE:
        host = net.get(hostname)
        host.cmd(
            f"dhclient -pf /tmp/dhclient-{hostname}.pid "
            f"-lf /tmp/dhclient-{hostname}.leases eth0 2>/dev/null"
        )
        ip = DHCP_LEASE[hostname][0]
        info(f"  {hostname} -> {ip} (DHCP)\n")


# ---------------------------------------------------------------------------
# VPN 地址
# ---------------------------------------------------------------------------
def configure_vpn_addresses(net):
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
# ACL
# ---------------------------------------------------------------------------
def configure_acl(net):
    info("*** Configuring ACL rules\n")

    core = net.get("c")
    ipt = core.cmd("command -v iptables").strip()
    if not ipt:
        info("!!! iptables not found; skipping ACL\n")
        return

    core.cmd(f"{ipt} -F FORWARD")
    core.cmd(f"{ipt} -t nat -F")
    core.cmd(f"{ipt} -P FORWARD ACCEPT")

    core.cmd(f"{ipt} -A FORWARD -d 10.0.100.10 -p tcp --dport 80 -j ACCEPT")
    core.cmd(f"{ipt} -A FORWARD -d 10.0.100.20 -p tcp --dport 21 -j ACCEPT")
    core.cmd(f"{ipt} -A FORWARD -d 10.0.100.0/24               -j ACCEPT")

    core.cmd(f"{ipt} -A FORWARD -s 10.0.40.0/24 -d 10.0.50.0/24 -j ACCEPT")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.40.0/24 -d 10.0.50.0/24 -j ACCEPT")
    core.cmd(f"{ipt} -A FORWARD -s 10.0.10.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.0.20.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.0.30.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.10.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.20.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.30.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD                 -d 10.0.50.0/24 -j DROP")

    core.cmd(f"{ipt} -A FORWARD -s 10.0.40.0/24 -d 10.0.60.0/24 -j ACCEPT")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.40.0/24 -d 10.0.60.0/24 -j ACCEPT")
    core.cmd(f"{ipt} -A FORWARD -s 10.0.10.0/24 -d 10.0.60.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.0.20.0/24 -d 10.0.60.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.0.30.0/24 -d 10.0.60.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.10.0/24 -d 10.0.60.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.20.0/24 -d 10.0.60.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD -s 10.1.30.0/24 -d 10.0.60.0/24 -j DROP")
    core.cmd(f"{ipt} -A FORWARD                 -d 10.0.60.0/24 -j DROP")

    core.cmd(f"{ipt} -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT")

    info(core.cmd(f"{ipt} -vnL FORWARD --line-numbers"))


# ---------------------------------------------------------------------------
# Darkstat 监控
# ---------------------------------------------------------------------------
def start_darkstat(net):
    info("*** Starting Darkstat traffic monitor\n")

    core = net.get("c")
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
    info("*** Testing connectivity\n")

    ad1  = net.get("ad1")
    ao1  = net.get("ao1")
    bd1  = net.get("bd1")
    bo1  = net.get("bo1")
    ahr1 = net.get("ahr1")

    r = ad1.cmd("ping -c 2 -W 2 10.0.10.254")
    info(f"[A VLAN10] ad1 -> gw c-eth0.10:           {'OK' if '0%' in r else 'FAIL'}\n")

    r = bd1.cmd("ping -c 2 -W 2 10.1.10.254")
    info(f"[B VLAN10] bd1 -> gw c-eth2.10:           {'OK' if '0%' in r else 'FAIL'}\n")

    r = ad1.cmd("ping -c 2 -W 2 10.0.20.1")
    info(f"[A 10->20] ad1 -> at1 (inter-VLAN):       {'OK' if '0%' in r else 'FAIL'}\n")

    r = bd1.cmd("ping -c 2 -W 2 10.1.20.1")
    info(f"[B 10->20] bd1 -> bt1 (inter-VLAN):       {'OK' if '0%' in r else 'FAIL'}\n")

    r = ad1.cmd("ping -c 2 -W 2 10.1.10.1")
    info(f"[A->B] ad1 (10.0.10.1) -> bd1 (10.1.10.1):{'OK' if '0%' in r else 'FAIL'}\n")

    r = bd1.cmd("ping -c 2 -W 2 10.0.10.1")
    info(f"[B->A] bd1 (10.1.10.1) -> ad1 (10.0.10.1):{'OK' if '0%' in r else 'FAIL'}\n")

    r = ad1.cmd("curl -s --connect-timeout 3 http://10.0.100.10")
    info(f"[A->Server] ad1 -> Web:                   {'OK' if 'Web Server' in r else 'FAIL'}\n")

    r = bd1.cmd("curl -s --connect-timeout 3 http://10.0.100.10")
    info(f"[B->Server] bd1 -> Web:                   {'OK' if 'Web Server' in r else 'FAIL'}\n")

    r = ad1.cmd("ping -c 2 -W 2 10.0.50.1")
    blocked = "100% packet loss" in r or "0 received" in r
    info(f"[ACL] ad1 (A-Dorm) -> ahr1 (A-HR):        {'BLOCKED (ok)' if blocked else 'ALLOWED (!)'}\n")

    r = bd1.cmd("ping -c 2 -W 2 10.0.50.1")
    blocked = "100% packet loss" in r or "0 received" in r
    info(f"[ACL] bd1 (B-Dorm) -> ahr1 (A-HR):        {'BLOCKED (ok)' if blocked else 'ALLOWED (!)'}\n")

    r = ao1.cmd("ping -c 2 -W 2 10.0.50.1")
    info(f"[ACL] ao1 (A-Office) -> ahr1 (A-HR):      {'OK' if '0%' in r else 'FAIL'}\n")

    r = bo1.cmd("ping -c 2 -W 2 10.0.50.1")
    info(f"[ACL] bo1 (B-Office) -> ahr1 (A-HR):      {'OK' if '0%' in r else 'FAIL'}\n")

    r = ad1.cmd("ping -c 2 -W 2 10.0.60.1")
    blocked = "100% packet loss" in r or "0 received" in r
    info(f"[ACL] ad1 (A-Dorm) -> afn1 (A-Finance):   {'BLOCKED (ok)' if blocked else 'ALLOWED (!)'}\n")

    r = bo1.cmd("ping -c 2 -W 2 10.0.60.1")
    info(f"[ACL] bo1 (B-Office) -> afn1 (A-Finance): {'OK' if '0%' in r else 'FAIL'}\n")


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
        configure_switches(net)
        configure_vlan_routing(net)
        configure_dhcp(net)
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
        info("  All campus hosts obtain IPs via DHCP (dnsmasq on c)\n")
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
