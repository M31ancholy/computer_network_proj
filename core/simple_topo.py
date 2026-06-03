#!/usr/bin/env python3
"""
简化版校园网拓扑 - 用于快速测试
功能：
1. 基本网络拓扑
2. 简单的路由配置
3. 访问控制
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import Controller, OVSKernelSwitch, Host
from mininet.cli import CLI
from mininet.log import setLogLevel, info


class SimpleCampusTopo(Topo):
    """简化版校园网络拓扑"""

    def build(self):
        # 核心交换机
        core = self.addSwitch("s0")

        # 部门交换机
        dorm_sw = self.addSwitch("s1")  # 学生宿舍
        teaching_sw = self.addSwitch("s2")  # 教学楼
        hr_sw = self.addSwitch("s3")  # 人事处（受限）
        server_sw = self.addSwitch("s4")  # 服务器区

        # 学生宿舍主机 - 10.0.1.0/24
        h1 = self.addHost("h1", ip="10.0.1.1/24")
        h2 = self.addHost("h2", ip="10.0.1.2/24")

        # 教学楼主机 - 10.0.2.0/24
        h3 = self.addHost("h3", ip="10.0.2.1/24")

        # 人事处主机 - 10.0.3.0/24（受限）
        h4 = self.addHost("h4", ip="10.0.3.1/24")

        # Web 服务器 - 10.0.100.0/24
        web = self.addHost("web", ip="10.0.100.10/24")

        # 连接到核心
        self.addLink(dorm_sw, core)
        self.addLink(teaching_sw, core)
        self.addLink(hr_sw, core)
        self.addLink(server_sw, core)

        # 主机连接
        self.addLink(h1, dorm_sw)
        self.addLink(h2, dorm_sw)
        self.addLink(h3, teaching_sw)
        self.addLink(h4, hr_sw)
        self.addLink(web, server_sw)


def configure_network(net):
    """配置网络路由和访问控制"""
    info("*** 配置网络\n")

    core = net.get("s0")

    # 启用 IP 转发
    core.cmd("sysctl -w net.ipv4.ip_forward=1")

    # 配置核心交换机作为路由器
    # 给核心交换机的各个接口配置 IP（作为网关）
    interfaces = core.intfList()
    info(f"核心交换机接口: {[str(i) for i in interfaces]}\n")

    # 配置每个主机的主机路由
    for host in net.hosts:
        info(f"配置主机 {host.name}...\n")

        # 根据主机所在网段配置默认网关
        if host.name in ["h1", "h2"]:
            host.cmd("route add default gw 10.0.1.254")
        elif host.name == "h3":
            host.cmd("route add default gw 10.0.2.254")
        elif host.name == "h4":
            host.cmd("route add default gw 10.0.3.254")
        elif host.name == "web":
            host.cmd("route add default gw 10.0.100.254")

    # 配置访问控制（使用 iptables）
    # 人事处（10.0.3.0/24）限制访问
    core.cmd("iptables -F")
    core.cmd("iptables -P FORWARD ACCEPT")

    # 阻止学生宿舍访问人事处
    core.cmd("iptables -A FORWARD -s 10.0.1.0/24 -d 10.0.3.0/24 -j DROP")
    info("访问控制已配置：学生宿舍无法访问人事处\n")


def test_network(net):
    """测试网络"""
    info("\n*** 测试网络\n")

    h1 = net.get("h1")
    h3 = net.get("h3")
    h4 = net.get("h4")
    web = net.get("web")

    # 启动 Web 服务
    web.cmd("python3 -m http.server 80 &")
    info("Web 服务器已启动\n")

    # 测试二层互通
    info("--- 测试同一部门内互通\n")
    result = h1.cmd("ping -c 2 10.0.1.2")
    info(
        f"h1 -> h2: {'成功' if '0% packet loss' in result or '2 packets transmitted' in result else '失败'}\n"
    )

    # 测试三层互通
    info("--- 测试跨部门互通\n")
    result = h1.cmd("ping -c 2 10.0.2.1")
    info(
        f"学生宿舍 -> 教学楼: {'成功' if '0% packet loss' in result or '2 packets transmitted' in result else '失败'}\n"
    )

    # 测试访问控制
    info("--- 测试访问控制\n")
    result = h1.cmd("ping -c 2 10.0.3.1")
    info(
        f"学生宿舍 -> 人事处: {'拒绝（符合预期）' if '100% packet loss' in result or '0 packets received' in result else '意外成功'}\n"
    )


def run():
    """主函数"""
    setLogLevel("info")

    info("*** 创建简化版校园网络\n")
    topo = SimpleCampusTopo()
    net = Mininet(topo=topo, controller=Controller)

    info("*** 启动网络\n")
    net.start()

    try:
        configure_network(net)
        test_network(net)

        info("\n*** 进入 Mininet CLI\n")
        info("常用命令:\n")
        info("  - nodes: 查看节点\n")
        info("  - h1 ping h3: 测试连通\n")
        info("  - exit: 退出\n\n")

        CLI(net)
    finally:
        info("*** 停止网络\n")
        net.stop()


if __name__ == "__main__":
    run()
