#!/usr/bin/env python3
"""
校园网拓扑 - 基于 Mininet
功能：
1. 每个部门内部二层互通（VLAN）
2. 部门间三层互通（路由）
3. Web/FTP 服务器访问
4. 人事处、财务处访问控制
"""

# 这是第一个版本能用的 但是路由器的实现有点太简陋了，该版本仅用于存档

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import Controller, OVSKernelSwitch, Host
from mininet.node import OVSController
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.util import dumpNodeConnections
import subprocess
import os


class CampusNetworkTopo(Topo):
    """校园网络拓扑定义"""

    def build(self):

        # ==================== 核心层 ====================
        # 核心交换机（支持三层路由）
        core_switch = self.addSwitch("c", dpid="0000000000000001")

        # ==================== 汇聚层 - 部门交换机 ====================
        dorm_switch = self.addSwitch("ds", dpid="0000000000000010")       # 宿舍 VLAN10
        teaching_switch = self.addSwitch("ts", dpid="0000000000000020")   # 教学楼 VLAN20
        library_switch = self.addSwitch("ls", dpid="0000000000000030")    # 图书馆 VLAN30
        office_switch = self.addSwitch("os", dpid="0000000000000040")     # 办公楼 VLAN40
        hr_switch = self.addSwitch("hrs", dpid="0000000000000050")        # 人事处 VLAN50
        finance_switch = self.addSwitch("fns", dpid="0000000000000060")   # 财务处 VLAN60
        server_switch = self.addSwitch("ss", dpid="0000000000000100")     # 服务器 VLAN100

        # ==================== 接入层 - 主机 ====================
        # 学生宿舍主机
        dorm_hosts = []
        for i in range(1, 4):
            host = self.addHost(
                f"d{i}",
                ip=f"10.0.10.{i}/24",
                mac=f"00:00:00:00:10:0{i}",
                defaultRoute="via 10.0.10.254",
            )
            dorm_hosts.append(host)

        # 教学楼主机
        teaching_hosts = []
        for i in range(1, 4):
            host = self.addHost(
                f"t{i}",
                ip=f"10.0.20.{i}/24",
                mac=f"00:00:00:00:20:0{i}",
                defaultRoute="via 10.0.20.254",
            )
            teaching_hosts.append(host)

        # 图书馆主机
        library_hosts = []
        for i in range(1, 3):
            host = self.addHost(
                f"l{i}",
                ip=f"10.0.30.{i}/24",
                mac=f"00:00:00:00:30:0{i}",
                defaultRoute="via 10.0.30.254",
            )
            library_hosts.append(host)

        # 办公楼主机
        office_hosts = []
        for i in range(1, 3):
            host = self.addHost(
                f"o{i}",
                ip=f"10.0.40.{i}/24",
                mac=f"00:00:00:00:40:0{i}",
                defaultRoute="via 10.0.40.254",
            )
            office_hosts.append(host)

        # 人事处主机（受限）
        hr_hosts = []
        for i in range(1, 3):
            host = self.addHost(
                f"hr{i}",
                ip=f"10.0.50.{i}/24",
                mac=f"00:00:00:00:50:0{i}",
                defaultRoute="via 10.0.50.254",
            )
            hr_hosts.append(host)

        # 财务处主机（受限）
        finance_hosts = []
        for i in range(1, 3):
            host = self.addHost(
                f"fn{i}",
                ip=f"10.0.60.{i}/24",
                mac=f"00:00:00:00:60:0{i}",
                defaultRoute="via 10.0.60.254",
            )
            finance_hosts.append(host)

        # 服务器
        web_server = self.addHost(
            "ws",
            ip="10.0.100.10/24",
            mac="00:00:00:00:100:01",
            defaultRoute="via 10.0.100.254",
        )
        ftp_server = self.addHost(
            "fs",
            ip="10.0.100.20/24",
            mac="00:00:00:00:100:02",
            defaultRoute="via 10.0.100.254",
        )

        # ==================== 链路连接 ====================
        # 交换机 → 核心
        self.addLink(dorm_switch, core_switch)
        self.addLink(teaching_switch, core_switch)
        self.addLink(library_switch, core_switch)
        self.addLink(office_switch, core_switch)
        self.addLink(hr_switch, core_switch)
        self.addLink(finance_switch, core_switch)
        self.addLink(server_switch, core_switch)

        # 主机 → 部门交换机
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

        # 服务器 → 服务器交换机
        self.addLink(web_server, server_switch)
        self.addLink(ftp_server, server_switch)


def configure_stp(net):
    switches = ["ds", "ts", "ls", "os", "hrs", "fns", "ss"]
    for name in switches:
        sw = net.get(name)
        sw.cmd(f"ovs-vsctl set bridge {name} stp_enable=true")


def configure_routing(net):
    """配置核心交换机的三层路由"""
    info("*** 配置三层路由\n")

    core = net.get("c")
    core.cmd("sysctl -w net.ipv4.ip_forward=1")

    interfaces = core.intfList()
    info(f"核心交换机接口: {[str(i) for i in interfaces]}\n")


def configure_acl(net):
    """配置访问控制列表（ACL）"""
    info("*** 配置访问控制\n")

    core = net.get("c")

    # 清空规则
    core.cmd("iptables -F")
    core.cmd("iptables -X")
    core.cmd("iptables -P FORWARD ACCEPT")

    # 人事处 VLAN 50 — 仅允许办公楼访问
    core.cmd("iptables -A FORWARD -s 10.0.50.0/24 -j ACCEPT")
    core.cmd("iptables -A FORWARD -d 10.0.50.0/24 -s 10.0.40.0/24 -j ACCEPT")
    core.cmd("iptables -A FORWARD -d 10.0.50.0/24 -j DROP")

    # 财务处 VLAN 60 — 仅允许办公楼访问
    core.cmd("iptables -A FORWARD -s 10.0.60.0/24 -j ACCEPT")
    core.cmd("iptables -A FORWARD -d 10.0.60.0/24 -s 10.0.40.0/24 -j ACCEPT")
    core.cmd("iptables -A FORWARD -d 10.0.60.0/24 -j DROP")

    info("访问控制规则已配置\n")


def start_services(net):
    """启动 Web 和 FTP 服务器"""
    info("*** 启动网络服务\n")

    ws = net.get("ws")
    ws.cmd("mkdir -p /var/www/html")
    ws.cmd('echo "<h1>Campus Web Server</h1>" > /var/www/html/index.html')
    ws.cmd("python3 -m http.server 80 &")
    info("Web 服务器已启动 (http://10.0.100.10)\n")

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
    info("FTP 服务器已启动 (ftp://10.0.100.20)\n")


def test_connectivity(net):
    """测试网络连通性"""
    info("*** 测试网络连通性\n")

    # 同部门二层互通
    info("--- 测试二层互通（同一部门）\n")
    d1 = net.get("d1")
    result = d1.cmd("ping -c 2 10.0.10.2")
    ok = "成功" if "2 packets transmitted" in result else "失败"
    info(f"学生宿舍 d1 -> d2: {ok}\n")

    # 跨部门三层互通
    info("--- 测试三层互通（跨部门）\n")
    result = d1.cmd("ping -c 2 10.0.20.1")
    ok = "成功" if "2 packets transmitted" in result else "失败"
    info(f"学生宿舍 -> 教学楼: {ok}\n")

    # Web 服务器
    info("--- 测试 Web 服务器访问\n")
    result = d1.cmd("curl -s http://10.0.100.10")
    ok = "成功" if "Campus Web Server" in result else "失败"
    info(f"学生宿舍访问 Web: {ok}\n")

    # 访问控制
    info("--- 测试访问控制（应该失败）\n")
    result = d1.cmd("ping -c 2 10.0.50.1")
    ok = "拒绝（符合预期）" if ("0 packets received" in result or "100% packet loss" in result) else "意外成功"
    info(f"学生宿舍 -> 人事处: {ok}\n")


def run():
    """主运行函数"""
    setLogLevel("info")

    info("*** 创建校园网络拓扑\n")
    topo = CampusNetworkTopo()

    net = Mininet(
        topo=topo,
        controller=OVSController,
        switch=OVSKernelSwitch,
        autoSetMacs=True,
        autoStaticArp=True,
    )

    info("*** 启动网络\n")
    net.start()

    info("*** 网络节点信息\n")
    dumpNodeConnections(net.hosts)

    try:
        configure_stp(net)
        configure_routing(net)
        configure_acl(net)
        start_services(net)
        test_connectivity(net)

        info("*** 进入 Mininet CLI (输入 help 查看命令，输入 exit 退出)\n")
        info("常用命令:\n")
        info("  - nodes: 查看所有节点\n")
        info("  - d1 ping t1: 测试宿舍到教学楼\n")
        info("  - d1 curl 10.0.100.10: 访问 Web 服务器\n")
        info("  - exit: 退出\n\n")

        CLI(net)

    except KeyboardInterrupt:
        info("\n*** 收到中断信号\n")
    finally:
        info("*** 停止网络\n")
        net.stop()


if __name__ == "__main__":
    run()
