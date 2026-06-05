#!/usr/bin/env python3
"""
校园网拓扑 - 基于 Mininet（修复版 + 详细计时）
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


# ============================ 计时工具 ============================
class Timer:
    """精确计时器：自动记录每个阶段起止时间"""

    def __init__(self):
        self.records = []          # [(名称, 开始时间, 结束时间), ...]
        self.current_step = None   # 当前正在计时的步骤名
        self.current_start = None  # 当前步骤的开始时间

    def start(self, step_name):
        """开始一个步骤的计时（自动结束上一个未结束的步骤）"""
        now = time.time()
        # 如果上一个步骤还在计时，自动结束它
        if self.current_step is not None:
            self.records.append((self.current_step, self.current_start, now))
        self.current_step = step_name
        self.current_start = now

    def stop(self):
        """结束当前步骤的计时"""
        if self.current_step is not None:
            self.records.append((self.current_step, self.current_start, time.time()))
            self.current_step = None
            self.current_start = None

    def elapsed(self, step_name):
        """获取某个步骤的耗时（秒），未结束则用当前时间算"""
        for name, start, end in self.records:
            if name == step_name:
                return end - start
        return None

    def total(self):
        """总耗时（从第一个开始到最后一个结束）"""
        if not self.records:
            return 0.0
        t0 = min(r[1] for r in self.records)
        t1 = max(r[2] for r in self.records)
        return t1 - t0

    def summary(self):
        """打印格式化的耗时汇总表"""
        if not self.records:
            return

        total_t = self.total()
        print("\n" + "=" * 58)
        print("  ⏱  运行耗时详细报告")
        print("=" * 58)
        print(f"  {'阶段':<22} {'耗时':>10} {'占比':>10}")
        print("  " + "-" * 44)

        for name, start, end in self.records:
            dur = end - start
            pct = (dur / total_t * 100) if total_t > 0 else 0
            # 格式化时间，>1秒显示 x.xxxs，<1秒显示 xxx.xms
            if dur >= 1:
                time_str = f"{dur:.3f}s"
            else:
                time_str = f"{dur*1000:.1f}ms"
            print(f"  {name:<22} {time_str:>10} {pct:>8.1f}%")

        print("  " + "-" * 44)
        if total_t >= 1:
            print(f"  {'总计':<22} {total_t:.3f}s{'':>10}")
        else:
            print(f"  {'总计':<22} {total_t*1000:.1f}ms{'':>10}")
        print("=" * 58 + "\n")


# ============================ 全局计时器 ============================
_timer = Timer()


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
        self.addLink(core_router, dorm_switch)        # c-eth0: 10.0.10.254
        self.addLink(core_router, teaching_switch)    # c-eth1: 10.0.20.254
        self.addLink(core_router, library_switch)     # c-eth2: 10.0.30.254
        self.addLink(core_router, office_switch)      # c-eth3: 10.0.40.254
        self.addLink(core_router, hr_switch)          # c-eth4: 10.0.50.254
        self.addLink(core_router, finance_switch)     # c-eth5: 10.0.60.254
        self.addLink(core_router, server_switch)      # c-eth6: 10.0.100.254
        self.addLink(core_router, vpn_inside_switch)  # c-eth7: 10.0.200.254

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
    """给核心路由器配 IP 地址"""
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
    """配置 VPN 服务器地址和路由"""
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
    """测试网络连通性（含每个子测试的独立计时）"""
    info("*** 测试网络连通性\n")

    d1 = net.get("d1")
    o1 = net.get("o1")

    # ----- 子测试 1: 同部门二层 -----
    _timer.start("  ├─ 同部门 (d1→d2)")
    result = d1.cmd("ping -c 1 -W 1 10.0.10.2")
    _timer.stop()
    info(f"  宿舍 d1 → d2: {'✓' if '1 received' in result else '✗'}\n")

    # ----- 子测试 2: 跨部门三层 -----
    _timer.start("  ├─ 跨部门 (d1→t1)")
    result = d1.cmd("ping -c 1 -W 1 10.0.20.1")
    _timer.stop()
    info(f"  宿舍 → 教学楼: {'✓' if '1 received' in result else '✗'}\n")

    # ----- 子测试 3: Web 服务器 -----
    _timer.start("  ├─ Web服务 (d1→ws)")
    result = d1.cmd("curl -s --connect-timeout 2 http://10.0.100.10")
    _timer.stop()
    info(f"  宿舍访问 Web: {'✓' if 'Campus Web Server' in result else '✗'}\n")

    # ----- 子测试 4: 访问控制-拒绝 -----
    _timer.start("  ├─ ACL拒绝 (d1→hr1)")
    result = d1.cmd("ping -c 1 -W 1 10.0.50.1")
    _timer.stop()
    info(f"  宿舍 → 人事处(应拒绝): {'✓ 已拒绝' if '0 received' in result or '100% packet loss' in result else '✗ 意外通了'}\n")

    # ----- 子测试 5: 访问控制-允许 -----
    _timer.start("  └─ ACL允许 (o1→hr1)")
    result = o1.cmd("ping -c 1 -W 1 10.0.50.1")
    _timer.stop()
    info(f"  办公楼 → 人事处(应允许): {'✓' if '1 received' in result else '✗'}\n")


def run():
    setLogLevel("info")

    # ==================== 1. 创建拓扑 ====================
    _timer.start("1. 创建拓扑")
    info("*** 创建校园网络拓扑\n")
    topo = CampusNetworkTopo()
    _timer.stop()

    # ==================== 2. 初始化 Mininet ====================
    _timer.start("2. 初始化网络")
    net = Mininet(
        topo=topo,
        switch=OVSKernelSwitch,
        autoSetMacs=True,
        autoStaticArp=True,
    )
    _timer.stop()

    # ==================== 3. 启动网络 ====================
    _timer.start("3. 启动网络")
    info("*** 启动网络\n")
    net.start()
    dumpNodeConnections(net.hosts)
    _timer.stop()

    try:
        # ==================== 4. 配置路由 ====================
        _timer.start("4. 配置路由")
        configure_routing(net)
        _timer.stop()

        # ==================== 5. 配置 ACL ====================
        _timer.start("5. 配置 ACL")
        configure_acl(net)
        _timer.stop()

        # ==================== 6. 启动服务 ====================
        _timer.start("6. 启动服务")
        start_services(net)
        _timer.stop()

        # ==================== 7. 配置 VPN ====================
        _timer.start("7. 配置 VPN")
        configure_vpn(net)
        _timer.stop()

        # ==================== 8. 连通性测试 ====================
        _timer.start("8. 连通性测试")
        test_connectivity(net)
        _timer.stop()

        # ==================== 打印计时汇总 ====================
        _timer.summary()

        # ==================== CLI 交互 ====================
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
