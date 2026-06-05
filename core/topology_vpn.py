#!/usr/bin/env python3
"""
校园网拓扑 - 基于 Mininet（VPN 扩展版）
功能：
1. 每个部门内部二层互通
2. 部门间三层互通
3. Web/FTP 服务器访问
4. 人事处、财务处访问控制
5. 外部用户通过 VPN 访问校园网
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import Controller, OVSKernelSwitch, Host
from mininet.node import OVSController
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.util import dumpNodeConnections
import time


class LinuxRouter(Host):
    """Linux 三层路由器，用来承担校园网网关。"""

    def config(self, **params):
        super().config(**params)
        self.cmd("sysctl -w net.ipv4.ip_forward=1")

    def terminate(self):
        self.cmd("sysctl -w net.ipv4.ip_forward=0")
        super().terminate()


class CampusNetworkVpnTopo(Topo):
    """带 VPN 外部接入的校园网络拓扑。"""

    def build(self):
        core_router = self.addHost("c", cls=LinuxRouter, ip=None)

        dorm_switch = self.addSwitch("ds", dpid="0000000000000010")
        teaching_switch = self.addSwitch("ts", dpid="0000000000000020")
        library_switch = self.addSwitch("ls", dpid="0000000000000030")
        office_switch = self.addSwitch("os", dpid="0000000000000040")
        hr_switch = self.addSwitch("hrs", dpid="0000000000000050")
        finance_switch = self.addSwitch("fns", dpid="0000000000000060")
        server_switch = self.addSwitch("ss", dpid="0000000000000100")
        vpn_inside_switch = self.addSwitch("vs", dpid="0000000000000200")
        internet_switch = self.addSwitch("is", dpid="0000000000000300")

        dorm_hosts = []
        for i in range(1, 4):
            dorm_hosts.append(
                self.addHost(
                    f"d{i}",
                    ip=f"10.0.10.{i}/24",
                    mac=f"00:00:00:00:10:0{i}",
                    defaultRoute="via 10.0.10.254",
                )
            )

        teaching_hosts = []
        for i in range(1, 4):
            teaching_hosts.append(
                self.addHost(
                    f"t{i}",
                    ip=f"10.0.20.{i}/24",
                    mac=f"00:00:00:00:20:0{i}",
                    defaultRoute="via 10.0.20.254",
                )
            )

        library_hosts = []
        for i in range(1, 3):
            library_hosts.append(
                self.addHost(
                    f"l{i}",
                    ip=f"10.0.30.{i}/24",
                    mac=f"00:00:00:00:30:0{i}",
                    defaultRoute="via 10.0.30.254",
                )
            )

        office_hosts = []
        for i in range(1, 3):
            office_hosts.append(
                self.addHost(
                    f"o{i}",
                    ip=f"10.0.40.{i}/24",
                    mac=f"00:00:00:00:40:0{i}",
                    defaultRoute="via 10.0.40.254",
                )
            )

        hr_hosts = []
        for i in range(1, 3):
            hr_hosts.append(
                self.addHost(
                    f"hr{i}",
                    ip=f"10.0.50.{i}/24",
                    mac=f"00:00:00:00:50:0{i}",
                    defaultRoute="via 10.0.50.254",
                )
            )

        finance_hosts = []
        for i in range(1, 3):
            finance_hosts.append(
                self.addHost(
                    f"fn{i}",
                    ip=f"10.0.60.{i}/24",
                    mac=f"00:00:00:00:60:0{i}",
                    defaultRoute="via 10.0.60.254",
                )
            )

        web_server = self.addHost(
            "ws",
            ip="10.0.100.10/24",
            mac="00:00:00:00:64:01",
            defaultRoute="via 10.0.100.254",
        )
        ftp_server = self.addHost(
            "fs",
            ip="10.0.100.20/24",
            mac="00:00:00:00:64:02",
            defaultRoute="via 10.0.100.254",
        )

        vpn_server = self.addHost("vpn", ip=None)
        external_client = self.addHost(
            "ex",
            ip="203.0.113.2/24",
            defaultRoute="via 203.0.113.1",
        )

        self.addLink(dorm_switch, core_router)
        self.addLink(teaching_switch, core_router)
        self.addLink(library_switch, core_router)
        self.addLink(office_switch, core_router)
        self.addLink(hr_switch, core_router)
        self.addLink(finance_switch, core_router)
        self.addLink(server_switch, core_router)
        self.addLink(vpn_inside_switch, core_router)

        for host in dorm_hosts:
            self.addLink(host, dorm_switch)
        for host in teaching_hosts:
            self.addLink(host, teaching_switch)
        for host in library_hosts:
            self.addLink(host, library_switch)
        for host in office_hosts:
            self.addLink(host, office_switch)
        for host in hr_hosts:
            self.addLink(host, hr_switch)
        for host in finance_hosts:
            self.addLink(host, finance_switch)

        self.addLink(web_server, server_switch)
        self.addLink(ftp_server, server_switch)

        self.addLink(vpn_server, internet_switch)
        self.addLink(external_client, internet_switch)
        self.addLink(vpn_server, vpn_inside_switch)


def configure_l2_switches(net):
    """配置二层交换机为独立学习转发模式。"""
    info("*** 配置二层交换机\n")

    for name in ["ds", "ts", "ls", "os", "hrs", "fns", "ss", "vs", "is"]:
        sw = net.get(name)
        sw.cmd(f"ovs-vsctl set-fail-mode {name} standalone")
        sw.cmd(f"ovs-ofctl add-flow {name} priority=0,actions=NORMAL")
        sw.cmd(f"ovs-vsctl set bridge {name} stp_enable=true")


def configure_routing(net):
    """配置核心路由器接口地址。"""
    info("*** 配置核心三层路由\n")

    core = net.get("c")
    core.cmd("sysctl -w net.ipv4.ip_forward=1")

    gateway_ips = {
        "c-eth0": "10.0.10.254/24",
        "c-eth1": "10.0.20.254/24",
        "c-eth2": "10.0.30.254/24",
        "c-eth3": "10.0.40.254/24",
        "c-eth4": "10.0.50.254/24",
        "c-eth5": "10.0.60.254/24",
        "c-eth6": "10.0.100.254/24",
        "c-eth7": "10.0.200.254/24",
    }

    for intf, ip in gateway_ips.items():
        core.cmd(f"ip addr flush dev {intf}")
        core.cmd(f"ip addr add {ip} dev {intf}")
        core.cmd(f"ip link set {intf} up")


# def configure_acl(net):
#     """配置校园网访问控制。"""
#     info("*** 配置访问控制 ACL\n")
#
#     core = net.get("c")
#     core.cmd("iptables -F")
#     core.cmd("iptables -X")
#     core.cmd("iptables -P FORWARD ACCEPT")
#     core.cmd("iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT")
#
#
#
#     core.cmd("iptables -A FORWARD -s 10.0.50.0/24 -j ACCEPT")
#     core.cmd("iptables -A FORWARD -d 10.0.50.0/24 -s 10.0.40.0/24 -j ACCEPT")
#     core.cmd("iptables -A FORWARD -d 10.0.50.0/24 -j DROP")
#
#     core.cmd("iptables -A FORWARD -s 10.0.60.0/24 -j ACCEPT")
#     core.cmd("iptables -A FORWARD -d 10.0.60.0/24 -s 10.0.40.0/24 -j ACCEPT")
#     core.cmd("iptables -A FORWARD -d 10.0.60.0/24 -j DROP")

def configure_acl(net):
    """配置校园网访问控制。"""
    info("*** 配置访问控制 ACL\n")

    core = net.get("c")

    # 清空旧规则
    core.cmd("iptables -F")
    core.cmd("iptables -X")
    core.cmd("iptables -t nat -F")

    # 默认允许转发，保证普通部门之间三层互通
    core.cmd("iptables -P FORWARD ACCEPT")

    # 清理连接跟踪，避免之前 ping 成功导致后面被 ESTABLISHED 放行
    core.cmd("conntrack -F 2>/dev/null || true")

    # =========================
    # 所有用户访问 Web/FTP 服务器
    # =========================
    core.cmd("iptables -A FORWARD -d 10.0.100.10 -p tcp --dport 80 -j ACCEPT")
    core.cmd("iptables -A FORWARD -d 10.0.100.20 -p tcp --dport 21 -j ACCEPT")

    # 如果 FTP 使用被动模式，简单实验可以直接允许访问服务器区
    core.cmd("iptables -A FORWARD -d 10.0.100.0/24 -j ACCEPT")

    # =========================
    # 人事处访问控制
    # 人事处网段：10.0.50.0/24
    # 只允许办公楼访问
    # =========================

    # 允许办公楼访问人事处
    core.cmd("iptables -A FORWARD -s 10.0.40.0/24 -d 10.0.50.0/24 -j ACCEPT")

    # 禁止学生宿舍访问人事处
    core.cmd("iptables -A FORWARD -s 10.0.10.0/24 -d 10.0.50.0/24 -j DROP")

    # 禁止教学楼访问人事处
    core.cmd("iptables -A FORWARD -s 10.0.20.0/24 -d 10.0.50.0/24 -j DROP")

    # 禁止图书馆访问人事处
    core.cmd("iptables -A FORWARD -s 10.0.30.0/24 -d 10.0.50.0/24 -j DROP")

    # 其他未授权区域访问人事处也拒绝
    core.cmd("iptables -A FORWARD -d 10.0.50.0/24 -j DROP")

    # =========================
    # 财务处访问控制
    # 财务处网段：10.0.60.0/24
    # 只允许办公楼访问
    # =========================

    # 允许办公楼访问财务处
    core.cmd("iptables -A FORWARD -s 10.0.40.0/24 -d 10.0.60.0/24 -j ACCEPT")

    # 禁止学生宿舍访问财务处
    core.cmd("iptables -A FORWARD -s 10.0.10.0/24 -d 10.0.60.0/24 -j DROP")

    # 禁止教学楼访问财务处
    core.cmd("iptables -A FORWARD -s 10.0.20.0/24 -d 10.0.60.0/24 -j DROP")

    # 禁止图书馆访问财务处
    core.cmd("iptables -A FORWARD -s 10.0.30.0/24 -d 10.0.60.0/24 -j DROP")

    # 其他未授权区域访问财务处也拒绝
    core.cmd("iptables -A FORWARD -d 10.0.60.0/24 -j DROP")

    # 允许已经建立的连接返回；必须放在受保护网段拒绝规则之后，避免旧连接状态绕过 ACL。
    core.cmd("iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT")

    # 打印 ACL，方便检查
    info(core.cmd("iptables -vnL FORWARD --line-numbers"))



def configure_vpn(net):
    """配置 OpenVPN 静态密钥隧道。"""
    info("*** 配置 VPN\n")

    vpn = net.get("vpn")
    ex = net.get("ex")

    vpn.cmd("ip addr flush dev vpn-eth0")
    vpn.cmd("ip addr add 203.0.113.1/24 dev vpn-eth0")
    vpn.cmd("ip link set vpn-eth0 up")
    vpn.cmd("ip addr flush dev vpn-eth1")
    vpn.cmd("ip addr add 10.0.200.10/24 dev vpn-eth1")
    vpn.cmd("ip link set vpn-eth1 up")
    vpn.cmd("ip route replace 10.0.0.0/16 via 10.0.200.254")

    ex.cmd("ip addr flush dev ex-eth0")
    ex.cmd("ip addr add 203.0.113.2/24 dev ex-eth0")
    ex.cmd("ip link set ex-eth0 up")
    ex.cmd("ip route replace default via 203.0.113.1")

    if not vpn.cmd("command -v openvpn").strip():
        info("!!! 未安装 openvpn，跳过 VPN 隧道启动\n")
        return False

    vpn.cmd("sysctl -w net.ipv4.ip_forward=1")
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

    vpn.cmd("iptables -F")
    vpn.cmd("iptables -t nat -F")
    vpn.cmd("iptables -P FORWARD ACCEPT")
    vpn.cmd("iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -d 10.0.0.0/16 -o vpn-eth1 -j MASQUERADE")
    vpn.cmd("iptables -A FORWARD -i tun0 -o vpn-eth1 -s 10.8.0.0/24 -d 10.0.0.0/16 -j ACCEPT")
    vpn.cmd("iptables -A FORWARD -i vpn-eth1 -o tun0 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT")

    vpn.cmd("openvpn --config /tmp/openvpn-server.conf --daemon --log /tmp/openvpn-server.log")
    time.sleep(1)
    ex.cmd("openvpn --config /tmp/openvpn-client.conf --daemon --log /tmp/openvpn-client.log")
    time.sleep(3)
    return True


def start_services(net):
    """启动 Web 和 FTP 服务。"""
    info("*** 启动网络服务\n")

    ws = net.get("ws")
    ws.cmd("mkdir -p /var/www/html")
    ws.cmd('echo "<h1>Campus Web Server</h1>" > /var/www/html/index.html')
    ws.cmd("python3 -m http.server 80 --directory /var/www/html &")

    fs = net.get("fs")
    fs.cmd("mkdir -p /var/ftp")
    fs.cmd('echo "Welcome to Campus FTP" > /var/ftp/welcome.txt')
    fs.cmd(
        "python3 -c \"import os; from pyftpdlib.authorizers import DummyAuthorizer; "
        "from pyftpdlib.handlers import FTPHandler; from pyftpdlib.servers import FTPServer; "
        "authorizer = DummyAuthorizer(); authorizer.add_anonymous('/var/ftp'); "
        "handler = FTPHandler; handler.authorizer = authorizer; "
        "server = FTPServer(('0.0.0.0', 21), handler); server.serve_forever()\" &"
    )


def test_connectivity(net):
    """输出关键连通性测试结果。"""
    info("*** 测试网络连通性\n")

    d1 = net.get("d1")
    o1 = net.get("o1")
    ex = net.get("ex")

    result = d1.cmd("ping -c 2 -W 1 10.0.10.2")
    info(f"学生宿舍 d1 -> d2: {'成功' if '0% packet loss' in result else '失败'}\n")

    result = d1.cmd("ping -c 2 -W 1 10.0.20.1")
    info(f"学生宿舍 -> 教学楼: {'成功' if '0% packet loss' in result else '失败'}\n")

    result = d1.cmd("curl -s --connect-timeout 2 http://10.0.100.10")
    info(f"学生宿舍访问 Web: {'成功' if 'Campus Web Server' in result else '失败'}\n")

    result = d1.cmd("ping -c 2 -W 1 10.0.50.1")
    info(f"学生宿舍 -> 人事处: {'拒绝（符合预期）' if '100% packet loss' in result else '意外成功'}\n")

    result = o1.cmd("ping -c 2 -W 1 10.0.50.1")
    info(f"办公楼 -> 人事处: {'成功' if '0% packet loss' in result else '失败'}\n")

    result = ex.cmd("ping -c 2 -W 2 10.8.0.1")
    info(f"外部客户端 ex -> VPN 隧道: {'成功' if '0% packet loss' in result else '失败'}\n")

    result = ex.cmd("curl -s --connect-timeout 3 http://10.0.100.10")
    info(f"外部客户端 ex 通过 VPN 访问 Web: {'成功' if 'Campus Web Server' in result else '失败'}\n")


def run():
    setLogLevel("info")

    info("*** 创建校园网络拓扑（VPN 版）\n")
    topo = CampusNetworkVpnTopo()
    net = Mininet(
        topo=topo,
        controller=Controller,
        switch=OVSKernelSwitch,
        autoSetMacs=True,
        autoStaticArp=True,
    )

    info("*** 启动网络\n")
    net.start()
    dumpNodeConnections(net.hosts)

    try:
        configure_l2_switches(net)
        configure_routing(net)
        configure_acl(net)
        start_services(net)
        configure_vpn(net)
        test_connectivity(net)
        CLI(net)
    except KeyboardInterrupt:
        info("\n*** 收到中断信号\n")
    finally:
        info("*** 停止网络\n")
        net.stop()


if __name__ == "__main__":
    run()
