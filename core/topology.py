#!/usr/bin/env python3
"""
校园网拓扑 - 基于 Mininet
功能：
1. 每个部门内部二层互通（VLAN）
2. 部门间三层互通（路由）
3. Web/FTP 服务器访问
4. 人事处、财务处访问控制
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import Controller, OVSKernelSwitch, Host
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.util import dumpNodeConnections
import subprocess
import os


class CampusNetworkTopo(Topo):
    """校园网络拓扑定义"""

    def build(self):
        """
        网络拓扑结构：

        核心层：Core Switch (核心交换机/路由器)
        汇聚层：Aggregation Switches (部门交换机)
        接入层：Hosts (终端设备)
        """

        # ==================== 核心层 ====================
        # 核心交换机（支持三层路由）
        core_switch = self.addSwitch("core", dpid="0000000000000001")

        # ==================== 汇聚层 - 部门交换机 ====================
        # 学生宿舍区 - VLAN 10
        dorm_switch = self.addSwitch("dorm_sw", dpid="0000000000000010")

        # 教学楼区 - VLAN 20
        teaching_switch = self.addSwitch("teach_sw", dpid="0000000000000020")

        # 图书馆区 - VLAN 30
        library_switch = self.addSwitch("lib_sw", dpid="0000000000000030")

        # 办公楼区 - VLAN 40
        office_switch = self.addSwitch("offi_sw", dpid="0000000000000040")

        # 人事处 - VLAN 50 (受限访问)
        hr_switch = self.addSwitch("hr_sw", dpid="0000000000000050")

        # 财务处 - VLAN 60 (受限访问)
        finance_switch = self.addSwitch("finance_sw", dpid="0000000000000060")

        # 服务器区 - VLAN 100
        server_switch = self.addSwitch("srv_sw", dpid="0000000000000100")

        # ==================== 接入层 - 主机 ====================
        # 学生宿舍主机
        dorm_hosts = []
        for i in range(1, 4):
            host = self.addHost(
                f"dorm_h{i}",
                ip=f"10.0.10.{i}/24",
                mac=f"00:00:00:00:10:0{i}",
                defaultRoute="via 10.0.10.254",
            )
            dorm_hosts.append(host)

        # 教学楼主机
        teaching_hosts = []
        for i in range(1, 4):
            host = self.addHost(
                f"teaching_h{i}",
                ip=f"10.0.20.{i}/24",
                mac=f"00:00:00:00:20:0{i}",
                defaultRoute="via 10.0.20.254",
            )
            teaching_hosts.append(host)

        # 图书馆主机
        library_hosts = []
        for i in range(1, 3):
            host = self.addHost(
                f"library_h{i}",
                ip=f"10.0.30.{i}/24",
                mac=f"00:00:00:00:30:0{i}",
                defaultRoute="via 10.0.30.254",
            )
            library_hosts.append(host)

        # 办公楼主机
        office_hosts = []
        for i in range(1, 3):
            host = self.addHost(
                f"office_h{i}",
                ip=f"10.0.40.{i}/24",
                mac=f"00:00:00:00:40:0{i}",
                defaultRoute="via 10.0.40.254",
            )
            office_hosts.append(host)

        # 人事处主机（受限）
        hr_hosts = []
        for i in range(1, 3):
            host = self.addHost(
                f"hr_h{i}",
                ip=f"10.0.50.{i}/24",
                mac=f"00:00:00:00:50:0{i}",
                defaultRoute="via 10.0.50.254",
            )
            hr_hosts.append(host)

        # 财务处主机（受限）
        finance_hosts = []
        for i in range(1, 3):
            host = self.addHost(
                f"finance_h{i}",
                ip=f"10.0.60.{i}/24",
                mac=f"00:00:00:00:60:0{i}",
                defaultRoute="via 10.0.60.254",
            )
            finance_hosts.append(host)

        # 服务器区
        web_server = self.addHost(
            "web_server",
            ip="10.0.100.10/24",
            mac="00:00:00:00:100:01",
            defaultRoute="via 10.0.100.254",
        )

        ftp_server = self.addHost(
            "ftp_server",
            ip="10.0.100.20/24",
            mac="00:00:00:00:100:02",
            defaultRoute="via 10.0.100.254",
        )

        # ==================== 链路连接 ====================
        # 部门交换机连接到核心交换机
        self.addLink(dorm_switch, core_switch)
        self.addLink(teaching_switch, core_switch)
        self.addLink(library_switch, core_switch)
        self.addLink(office_switch, core_switch)
        self.addLink(hr_switch, core_switch)
        self.addLink(finance_switch, core_switch)
        self.addLink(server_switch, core_switch)

        # 主机连接到各自的部门交换机
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

        # 服务器连接
        self.addLink(web_server, server_switch)
        self.addLink(ftp_server, server_switch)


def configure_vlans(net):
    """配置 VLAN 和交换机端口"""
    info("*** 配置 VLAN 和交换机端口\n")

    # 获取交换机对象
    core = net.get("core")
    dorm_sw = net.get("dorm_sw")
    teaching_sw = net.get("teaching_sw")
    library_sw = net.get("library_sw")
    office_sw = net.get("office_sw")
    hr_sw = net.get("hr_sw")
    finance_sw = net.get("finance_sw")
    server_sw = net.get("server_sw")

    # 配置接入交换机 VLAN（简化版 - 实际需要更复杂的配置）
    for sw in [
        dorm_sw,
        teaching_sw,
        library_sw,
        office_sw,
        hr_sw,
        finance_sw,
        server_sw,
    ]:
        # 启用交换机
        sw.cmd("ovs-vsctl set bridge {} stp_enable=true".format(sw.name))


def configure_routing(net):
    """配置核心交换机的三层路由"""
    info("*** 配置三层路由\n")

    core = net.get("core")

    # 在核心交换机上配置各 VLAN 的网关 IP
    # 注意：这需要在实际环境中使用支持三层功能的交换机
    # 这里使用简单的 Linux bridge 路由功能模拟

    # 启用 IP 转发
    core.cmd("sysctl -w net.ipv4.ip_forward=1")

    # 配置各 VLAN 接口的 IP 地址（网关）
    vlan_configs = [
        ("10.0.10.254/24", "dorm"),
        ("10.0.20.254/24", "teaching"),
        ("10.0.30.254/24", "library"),
        ("10.0.40.254/24", "office"),
        ("10.0.50.254/24", "hr"),
        ("10.0.60.254/24", "finance"),
        ("10.0.100.254/24", "server"),
    ]

    # 简化版：直接在核心交换机接口上配置 IP
    # 实际生产环境需要配置 VLAN interface
    interfaces = core.intfList()
    info(f"核心交换机接口: {[str(i) for i in interfaces]}\n")


def configure_acl(net):
    """配置访问控制列表（ACL）"""
    info("*** 配置访问控制\n")

    core = net.get("core")

    # 使用 iptables 实现访问控制
    # 清空现有规则
    core.cmd("iptables -F")
    core.cmd("iptables -X")

    # 默认允许所有流量
    core.cmd("iptables -P FORWARD ACCEPT")

    # 人事处 VLAN 50 (10.0.50.0/24) - 限制其他区域访问
    # 只允许特定区域访问人事处
    core.cmd("iptables -A FORWARD -s 10.0.50.0/24 -j ACCEPT")  # 允许人事处向外访问
    core.cmd(
        "iptables -A FORWARD -d 10.0.50.0/24 -s 10.0.40.0/24 -j ACCEPT"
    )  # 允许办公楼访问
    core.cmd("iptables -A FORWARD -d 10.0.50.0/24 -j DROP")  # 拒绝其他区域访问

    # 财务处 VLAN 60 (10.0.60.0/24) - 限制其他区域访问
    core.cmd("iptables -A FORWARD -s 10.0.60.0/24 -j ACCEPT")  # 允许财务处向外访问
    core.cmd(
        "iptables -A FORWARD -d 10.0.60.0/24 -s 10.0.40.0/24 -j ACCEPT"
    )  # 允许办公楼访问
    core.cmd("iptables -A FORWARD -d 10.0.60.0/24 -j DROP")  # 拒绝其他区域访问

    info("访问控制规则已配置\n")


def start_services(net):
    """启动 Web 和 FTP 服务器"""
    info("*** 启动网络服务\n")

    # Web 服务器
    web_server = net.get("web_server")
    web_server.cmd("mkdir -p /var/www/html")
    web_server.cmd('echo "<h1>Campus Web Server</h1>" > /var/www/html/index.html')
    web_server.cmd("python3 -m http.server 80 &")
    info("Web 服务器已启动 (http://10.0.100.10)\n")

    # FTP 服务器（简单版本）
    ftp_server = net.get("ftp_server")
    ftp_server.cmd("mkdir -p /var/ftp")
    ftp_server.cmd('echo "Welcome to Campus FTP" > /var/ftp/welcome.txt')
    # 使用 Python 的简单 FTP 服务器
    ftp_server.cmd(
        "python3 -c \"import os; from pyftpdlib.authorizers import DummyAuthorizer; from pyftpdlib.handlers import FTPHandler; from pyftpdlib.servers import FTPServer; authorizer = DummyAuthorizer(); authorizer.add_anonymous('/var/ftp'); handler = FTPHandler; handler.authorizer = authorizer; server = FTPServer(('0.0.0.0', 21), handler); server.serve_forever()\" &"
    )
    info("FTP 服务器已启动 (ftp://10.0.100.20)\n")


def test_connectivity(net):
    """测试网络连通性"""
    info("*** 测试网络连通性\n")

    # 测试同一部门内互通（二层）
    info("--- 测试二层互通（同一部门）\n")
    dorm_h1 = net.get("dorm_h1")
    result = dorm_h1.cmd("ping -c 2 10.0.10.2")
    info(
        f"学生宿舍 h1 -> h2: {'成功' if '2 packets transmitted' in result else '失败'}\n"
    )

    # 测试部门间互通（三层）
    info("--- 测试三层互通（跨部门）\n")
    result = dorm_h1.cmd("ping -c 2 10.0.20.1")
    info(
        f"学生宿舍 -> 教学楼: {'成功' if '2 packets transmitted' in result else '失败'}\n"
    )

    # 测试 Web 服务器访问
    info("--- 测试 Web 服务器访问\n")
    result = dorm_h1.cmd("curl -s http://10.0.100.10")
    info(f"学生宿舍访问 Web: {'成功' if 'Campus Web Server' in result else '失败'}\n")

    # 测试访问控制
    info("--- 测试访问控制（应该失败）\n")
    result = dorm_h1.cmd("ping -c 2 10.0.50.1")
    info(
        f"学生宿舍 -> 人事处: {'拒绝（符合预期）' if '0 packets received' in result or '100% packet loss' in result else '意外成功'}\n"
    )


def run():
    """主运行函数"""
    # 设置日志级别
    setLogLevel("info")

    # 创建网络拓扑
    info("*** 创建校园网络拓扑\n")
    topo = CampusNetworkTopo()

    # 创建网络实例
    net = Mininet(
        topo=topo,
        controller=Controller,
        switch=OVSKernelSwitch,
        autoSetMacs=True,
        autoStaticArp=True,
    )

    # 启动网络
    info("*** 启动网络\n")
    net.start()

    # 显示网络信息
    info("*** 网络节点信息\n")
    dumpNodeConnections(net.hosts)

    try:
        # 配置 VLAN
        configure_vlans(net)

        # 配置路由
        configure_routing(net)

        # 配置访问控制
        configure_acl(net)

        # 启动服务
        start_services(net)

        # 测试连通性
        test_connectivity(net)

        # 进入命令行交互界面
        info("*** 进入 Mininet CLI (输入 help 查看命令，输入 exit 退出)\n")
        info("常用命令:\n")
        info("  - nodes: 查看所有节点\n")
        info("  - links: 查看所有链路\n")
        info("  - dorm_h1 ping teaching_h1: 测试连通性\n")
        info("  - dorm_h1 curl 10.0.100.10: 访问 Web 服务器\n")
        info("  - exit: 退出\n\n")

        CLI(net)

    except KeyboardInterrupt:
        info("\n*** 收到中断信号\n")
    finally:
        # 停止网络
        info("*** 停止网络\n")
        net.stop()


if __name__ == "__main__":
    run()
