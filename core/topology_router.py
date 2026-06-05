#!/usr/bin/env python3
"""
Campus network topology with a Linux router as the core node.

This variant keeps the same department/server layout as topology.py, but
uses host c as the real layer-3 router for inter-department routing and ACLs.
"""
# 模拟了路由器的实现

from mininet.cli import CLI
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import Host, OVSController, OVSKernelSwitch
from mininet.topo import Topo
from mininet.util import dumpNodeConnections


class LinuxRouter(Host):
    """Linux host with IPv4 forwarding enabled."""

    def config(self, **params):
        super().config(**params)
        self.cmd("sysctl -w net.ipv4.ip_forward=1")

    def terminate(self):
        self.cmd("sysctl -w net.ipv4.ip_forward=0")
        super().terminate()


class CampusNetworkRouterTopo(Topo):
    """Campus network topology with c as a router."""

    def build(self):
        core_router = self.addHost("c", cls=LinuxRouter, ip=None)

        dorm_switch = self.addSwitch("ds", dpid="0000000000000010")
        teaching_switch = self.addSwitch("ts", dpid="0000000000000020")
        library_switch = self.addSwitch("ls", dpid="0000000000000030")
        office_switch = self.addSwitch("os", dpid="0000000000000040")
        hr_switch = self.addSwitch("hrs", dpid="0000000000000050")
        finance_switch = self.addSwitch("fns", dpid="0000000000000060")
        server_switch = self.addSwitch("ss", dpid="0000000000000100")

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

        self.addLink(dorm_switch, core_router)
        self.addLink(teaching_switch, core_router)
        self.addLink(library_switch, core_router)
        self.addLink(office_switch, core_router)
        self.addLink(hr_switch, core_router)
        self.addLink(finance_switch, core_router)
        self.addLink(server_switch, core_router)

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


def configure_routing(net):
    """Configure gateway IP addresses on the core router interfaces."""
    info("*** Configuring layer-3 routing\n")

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
    }

    for intf, ip in gateway_ips.items():
        core.cmd(f"ip addr flush dev {intf}")
        core.cmd(f"ip addr add {ip} dev {intf}")
        core.cmd(f"ip link set {intf} up")


def configure_acl(net):
    """Configure ACLs on the core router."""
    info("*** Configuring ACLs\n")

    core = net.get("c")
    core.cmd("iptables -F")
    core.cmd("iptables -X")
    core.cmd("iptables -P FORWARD ACCEPT")

    core.cmd("iptables -A FORWARD -s 10.0.50.0/24 -j ACCEPT")
    core.cmd("iptables -A FORWARD -d 10.0.50.0/24 -s 10.0.40.0/24 -j ACCEPT")
    core.cmd("iptables -A FORWARD -d 10.0.50.0/24 -j DROP")

    core.cmd("iptables -A FORWARD -s 10.0.60.0/24 -j ACCEPT")
    core.cmd("iptables -A FORWARD -d 10.0.60.0/24 -s 10.0.40.0/24 -j ACCEPT")
    core.cmd("iptables -A FORWARD -d 10.0.60.0/24 -j DROP")


def start_services(net):
    """Start Web and FTP services."""
    info("*** Starting network services\n")

    ws = net.get("ws")
    ws.cmd("mkdir -p /var/www/html")
    ws.cmd('echo "<h1>Campus Web Server</h1>" > /var/www/html/index.html')
    ws.cmd("python3 -m http.server 80 --directory /var/www/html &>/dev/null &")

    fs = net.get("fs")
    fs.cmd("mkdir -p /var/ftp")
    fs.cmd('echo "Welcome to Campus FTP" > /var/ftp/welcome.txt')
    fs.cmd(
        'python3 -c "'
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


def test_connectivity(net):
    """Run basic connectivity checks."""
    info("*** Testing connectivity\n")

    d1 = net.get("d1")
    o1 = net.get("o1")

    result = d1.cmd("ping -c 2 -W 1 10.0.10.2")
    info(f"Dorm d1 -> d2: {'success' if '0% packet loss' in result else 'failed'}\n")

    result = d1.cmd("ping -c 2 -W 1 10.0.20.1")
    info(f"Dorm -> teaching: {'success' if '0% packet loss' in result else 'failed'}\n")

    result = d1.cmd("curl -s --connect-timeout 2 http://10.0.100.10")
    info(f"Dorm -> Web: {'success' if 'Campus Web Server' in result else 'failed'}\n")

    result = d1.cmd("ping -c 2 -W 1 10.0.50.1")
    blocked = "100% packet loss" in result or "0 received" in result
    info(f"Dorm -> HR: {'blocked as expected' if blocked else 'unexpectedly allowed'}\n")

    result = o1.cmd("ping -c 2 -W 1 10.0.50.1")
    info(f"Office -> HR: {'success' if '0% packet loss' in result else 'failed'}\n")


def run():
    """Run the topology."""
    setLogLevel("info")

    info("*** Creating campus router topology\n")
    topo = CampusNetworkRouterTopo()

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
        configure_routing(net)
        configure_acl(net)
        start_services(net)
        test_connectivity(net)

        info("*** Entering Mininet CLI\n")
        info("Useful commands:\n")
        info("  d1 ping t1\n")
        info("  d1 curl 10.0.100.10\n")
        info("  o1 ping hr1\n")
        info("  d1 ping hr1\n")
        info("  exit\n\n")

        CLI(net)

    except KeyboardInterrupt:
        info("\n*** Interrupted\n")
    finally:
        info("*** Stopping network\n")
        net.stop()


if __name__ == "__main__":
    run()
