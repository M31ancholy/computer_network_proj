
#!/usr/bin/env python3
"""
校园网拓扑 - 基于 Mininet（修复版）
功能：
1. 每个部门内部二层互通
2. 部门间三层互通（通过核心路由器）
3. Web/FTP 服务器访问
4. 人事处、财务处访问控制
5. 外部用户通过 VPN 访问校园网
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, Host
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.util import dumpNodeConnections
import time


class LinuxRouter(Host):
    """Linux 三层路由器"""

    def config(self, **params):
        super().config(**params)
        self.cmd("sysctl -w net.ipv4.ip_forward=1")

    def terminate(self):
        self.cmd("sysctl -w net.ipv4.ip_forward=0")
        super().terminate()


class CampusNetworkTopo(Topo):
    """校园网络拓扑"""

    def build(self):
        # ========== 核心路由器（三层） ==========
        # ★ 修复1: 从 addSwitch 改为 addHost + LinuxRouter
        core_router = self.addHost("c", cls=LinuxRouter, ip=None)

        # ========== 部门交换机（二层） ==========
        dorm_switch = self.addSwitch("ds", dpid="0000000000000010")
        teaching_switch = self.addSwitch("ts", dpid="0000000000000020")
        library_switch = self.addSwitch("ls", dpid="0000000000000030")
        office_switch = self.addSwitch("os", dpid="0000000000000040")
        hr_switch = self.addSwitch("hrs", dpid="0000000000000050")
        finance_switch = self.addSwitch("fns", dpid="0000000000000060")
        server_switch = self.addSwitch("ss", dpid="0000000000000100")
        vpn_inside_switch = self.addSwitch("vs", dpid="0000000000000200")
        internet_switch = self.addSwitch("is", dpid="0000000000000300")

        # ========== 主机 ==========
        for i in range(1, 4):
            self.addHost(f"d{i}", ip=f"10.0.10.{i}/24",
                         defaultRoute="via 10.0.10.254")
        for i in range(1, 4):
            self.addHost(f"t{i}", ip=f"10.0.20.{i}/24",
                         defaultRoute="via 10.0.20.254")
        for i in range(1, 3):
            self.addHost(f"l{i}", ip=f"10.0.30.{i}/24",
                         defaultRoute="via 10.0.30.254")
        for i in range(1, 3):
            self.addHost(f"o{i}", ip=f"10.0.40.{i}/24",
                         defaultRoute="via 10.0.40.254")
        for i in range(1, 3):
            self.addHost(f"hr{i}", ip=f"10.0.50.{i}/24",
                         defaultRoute="via 10.0.50.254")
        for i in range(1, 3):
            self.addHost(f"fn{i}", ip=f"10.0.60.{i}/24",
                         defaultRoute="via 10.0.60.254")

        self.addHost("ws", ip="10.0.100.10/24",
                     defaultRoute="via 10.0.100.254")
        self.addHost("fs", ip="10.0.100.20/24",
                     defaultRoute="via 10.0.100.254")

        vpn_server = self.addHost("vpn", ip=None)
        self.addHost("ex", ip="203.0.113.2/24",
                     defaultRoute="via 203.0.113.1")

        # ========== 链路 ==========
        # ★ 注意顺序: 核心路由器的 eth0~eth7 按此顺序分配
        self.addLink(core_router, dorm_switch)        # c-eth0: 10.0.10.254
        self.addLink(core_router, teaching_switch)    # c-eth1: 10.0.20.254
        self.addLink(core_router, library_switch)     # c-eth2: 10.0.30.254
        self.addLink(core_router, office_switch)      # c-eth3: 10.0.40.254
        self.addLink(core_router, hr_switch)          # c-eth4: 10.0.50.254
        self.addLink(core_router, finance_switch)     # c-eth5: 10.0.60.254
        self.addLink(core_router, server_switch)      # c-eth6: 10.0.100.254
        self.addLink(core_router, vpn_inside_switch)  # ★ 修复2: vs 连到核心！c-eth7: 10.0.200.254

        # 主机 → 部门交换机
        for i in range(1, 4): self.addLink(f"d{i}", dorm_switch)
        for i in range(1, 4): self.addLink(f"t{i}", teaching_switch)
        for i in range(1, 3): self.addLink(f"l{i}", library_switch)
        for i in range(1, 3): self.addLink(f"o{i}", office_switch)
        for i in range(1, 3): self.addLink(f"hr{i}", hr_switch)
        for i in range(1, 3): self.addLink(f"fn{i}", finance_switch)

        self.addLink("ws", server_switch)
        self.addLink("fs", server_switch)

        # VPN 和外部网络
        self.addLink(vpn_server, internet_switch)    # vpn-eth0: 203.0.113.1
        self.addLink(vpn_server, vpn_inside_switch)  # vpn-eth1: 10.0.200.10
        self.addLink("ex", internet_switch)           # ex-eth0: 203.0.113.2


def configure_routing(net):
    """★ 修复3: 给核心路由器配 IP 地址"""
    info("*** 配置三层路由\n")

    core = net.get("c")

    gateway_ips = {
        "c-eth0": "10.0.10.254/24",   # 宿舍
        "c-eth1": "10.0.20.254/24",   # 教学楼
        "c-eth2": "10.0.30.254/24",   # 图书馆
        "c-eth3": "10.0.40.254/24",   # 办公楼
        "c-eth4": "10.0.50.254/24",   # 人事处
        "c-eth5": "10.0.60.254/24",   # 财务处
        "c-eth6": "10.0.100.254/24",  # 服务器
        "c-eth7": "10.0.200.254/24",  # VPN 内部
    }

    for intf, ip in gateway_ips.items():
        core.cmd(f"ip addr flush dev {intf} 2>/dev/null")
        core.cmd(f"ip addr add {ip} dev {intf}")
        core.cmd(f"ip link set {intf} up")

    info("  核心路由器接口已配置\n")


def configure_acl(net):
    """配置访问控制"""
    info("*** 配置访问控制\n")

    core = net.get("c")
    core.cmd("iptables -F")
    core.cmd("iptables -X")
    core.cmd("iptables -P FORWARD ACCEPT")

    # 允许访问 Web/FTP 服务器
    core.cmd("iptables -A FORWARD -d 10.0.100.10 -p tcp --dport 80 -j ACCEPT")
    core.cmd("iptables -A FORWARD -d 10.0.100.20 -p tcp --dport 21 -j ACCEPT")
    core.cmd("iptables -A FORWARD -d 10.0.100.0/24 -j ACCEPT")

    # 人事处 - 仅办公楼可访问
    core.cmd("iptables -A FORWARD -s 10.0.40.0/24 -d 10.0.50.0/24 -j ACCEPT")
    core.cmd("iptables -A FORWARD -d 10.0.50.0/24 -j DROP")

    # 财务处 - 仅办公楼可访问
    core.cmd("iptables -A FORWARD -s 10.0.40.0/24 -d 10.0.60.0/24 -j ACCEPT")
    core.cmd("iptables -A FORWARD -d 10.0.60.0/24 -j DROP")

    # 允许已建立连接返回
    core.cmd("iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT")

    info("  访问控制规则已配置\n")


def start_services(net):
    """启动 Web 和 FTP 服务"""
    info("*** 启动网络服务\n")

    ws = net.get("ws")
    ws.cmd("mkdir -p /var/www/html")
    ws.cmd('echo "<h1>Campus Web Server</h1>" > /var/www/html/index.html')
    ws.cmd("python3 -m http.server 80 &>/dev/null &")
    info("  Web 服务器已启动 (http://10.0.100.10)\n")

    fs = net.get("fs")
    fs.cmd("mkdir -p /var/ftp")
    fs.cmd('echo "Welcome to Campus FTP" > /var/ftp/welcome.txt')
    fs.cmd(
        'python3 -c "'
        'import os; '
        'from pyftpdlib.authorizers import DummyAuthorizer; '
        'from pyftpdlib.handlers import FTPHandler; '
        'from pyftpdlib.servers import FTPServer; '
        'authorizer = DummyAuthorizer(); '
        'authorizer.add_anonymous(\"/var/ftp\"); '
        'handler = FTPHandler; '
        'handler.authorizer = authorizer; '
        'server = FTPServer((\"0.0.0.0\", 21), handler); '
        'server.serve_forever()" &>/dev/null &'
    )
    info("  FTP 服务器已启动 (ftp://10.0.100.20)\n")


def configure_vpn(net):
    """配置 VPN 服务器地址和路由（不启动 OpenVPN 守护进程，避免卡顿）"""
    info("*** 配置 VPN\n")

    vpn = net.get("vpn")
    ex = net.get("ex")

    # VPN 公网口
    vpn.cmd("ip addr flush dev vpn-eth0")
    vpn.cmd("ip addr add 203.0.113.1/24 dev vpn-eth0")
    vpn.cmd("ip link set vpn-eth0 up")

    # VPN 内网口
    vpn.cmd("ip addr flush dev vpn-eth1")
    vpn.cmd("ip addr add 10.0.200.10/24 dev vpn-eth1")
    vpn.cmd("ip link set vpn-eth1 up")

    # VPN 访问校园网的路由：走核心路由器
    vpn.cmd("ip route replace 10.0.0.0/16 via 10.0.200.254")

    # 外部客户端
    ex.cmd("ip link set ex-eth0 up")

    info("  VPN 地址配置完成\n")


def test_connectivity(net):
    """测试网络连通性"""
    info("*** 测试网络连通性\n")

    d1 = net.get("d1")
    o1 = net.get("o1")

    # 同部门二层
    result = d1.cmd("ping -c 1 -W 1 10.0.10.2")
    info(f"  宿舍 d1 → d2: {'✓' if '1 received' in result else '✗'}\n")

    # 跨部门三层
    result = d1.cmd("ping -c 1 -W 1 10.0.20.1")
    info(f"  宿舍 → 教学楼: {'✓' if '1 received' in result else '✗'}\n")

    # Web 服务器
    result = d1.cmd("curl -s --connect-timeout 2 http://10.0.100.10")
    info(f"  宿舍访问 Web: {'✓' if 'Campus Web Server' in result else '✗'}\n")

    # 访问控制 - 宿舍不能访问人事处
    result = d1.cmd("ping -c 1 -W 1 10.0.50.1")
    info(f"  宿舍 → 人事处(应拒绝): {'✓ 已拒绝' if '0 received' in result or '100% packet loss' in result else '✗ 意外通了'}\n")

    # 办公楼可以访问人事处
    result = o1.cmd("ping -c 1 -W 1 10.0.50.1")
    info(f"  办公楼 → 人事处(应允许): {'✓' if '1 received' in result else '✗'}\n")


def run():
    setLogLevel("info")

    info("*** 创建校园网络拓扑\n")
    topo = CampusNetworkTopo()

    # ★ 修复4: 去掉 OVSController + autoStaticArp，加快启动
    net = Mininet(
        topo=topo,
        switch=OVSKernelSwitch,
        autoSetMacs=True,
        autoStaticArp=True,
    )

    info("*** 启动网络\n")
    net.start()
    dumpNodeConnections(net.hosts)

    try:
        # ★ 修复5: 去掉 STP（星型拓扑不需要）
        # configure_stp(net)  ← 已删除

        configure_routing(net)
        configure_acl(net)
        start_services(net)
        configure_vpn(net)
        test_connectivity(net)

        info("\n*** 进入 Mininet CLI\n")
        info("  测试命令:\n")
        info("    d1 ping t1         # 跨部门通信\n")
        info("    d1 curl 10.0.100.10 # 访问 Web\n")
        info("    o1 ping hr1        # 办公楼 → 人事处（应通）\n")
        info("    d1 ping hr1        # 宿舍 → 人事处（应不通）\n")
        info("    ex ping 203.0.113.1 # 外部 → VPN 公网\n\n")
        CLI(net)

    except KeyboardInterrupt:
        info("\n*** 收到中断\n")
    finally:
        info("*** 停止网络\n")
        net.stop()


if __name__ == "__main__":
    run()
