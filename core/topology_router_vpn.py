#!/usr/bin/env python3
"""
Campus network topology with a Linux core router and VPN access.

This variant extends topology_router.py with the VPN-side topology from
topology_vpn.py while keeping c as a real Linux router.
"""

import time

from mininet.cli import CLI
from mininet.examples.linuxrouter import LinuxRouter
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import Host, OVSController, OVSKernelSwitch
from mininet.topo import Topo
from mininet.util import dumpNodeConnections


COMMAND_CHECKS = {
    "iptables": "command -v iptables",
    "openvpn": "command -v openvpn",
}
COMMAND_ERRORS = {
    "iptables": "Missing iptables; install it with: sudo apt install iptables",
}




class CampusNetworkRouterVpnTopo(Topo):
    """Campus network topology with VPN external access."""

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


def require_cmd(node, command, install_hint):
    """Return a command path or fail loudly instead of silently skipping ACLs."""
    lookup = COMMAND_CHECKS.get(command, f"command -v {command}")
    path = node.cmd(lookup).strip()
    if not path:
        raise RuntimeError(COMMAND_ERRORS.get(command, f"Missing {command}; {install_hint}"))
    return path


def optional_cmd(node, command):
    lookup = COMMAND_CHECKS.get(command, f"command -v {command}")
    return node.cmd(lookup).strip()


def configure_l2_switches(net):
    """Configure OVS switches for standalone layer-2 forwarding."""
    info("*** Configuring layer-2 switches\n")

    for name in ["ds", "ts", "ls", "os", "hrs", "fns", "ss", "vs", "is"]:
        sw = net.get(name)
        sw.cmd(f"ovs-vsctl set-fail-mode {name} standalone")
        sw.cmd(f"ovs-ofctl add-flow {name} priority=0,actions=NORMAL")


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
        "c-eth7": "10.0.200.254/24",
    }

    for intf, ip in gateway_ips.items():
        core.cmd(f"ip addr flush dev {intf}")
        core.cmd(f"ip addr add {ip} dev {intf}")
        core.cmd(f"ip link set {intf} up")


def configure_acl(net):
    """Configure ACLs on the core router."""
    info("*** Configuring ACLs\n")

    core = net.get("c")
    iptables = require_cmd(core, "iptables", "install it with: sudo apt install iptables")
    conntrack = optional_cmd(core, "conntrack")

    core.cmd(f"{iptables} -F")
    core.cmd(f"{iptables} -X")
    core.cmd(f"{iptables} -t nat -F")
    core.cmd(f"{iptables} -P FORWARD ACCEPT")
    if conntrack:
        core.cmd(f"{conntrack} -F 2>/dev/null || true")

    core.cmd(f"{iptables} -A FORWARD -d 10.0.100.10 -p tcp --dport 80 -j ACCEPT")
    core.cmd(f"{iptables} -A FORWARD -d 10.0.100.20 -p tcp --dport 21 -j ACCEPT")
    core.cmd(f"{iptables} -A FORWARD -d 10.0.100.0/24 -j ACCEPT")

    core.cmd(f"{iptables} -A FORWARD -s 10.0.40.0/24 -d 10.0.50.0/24 -j ACCEPT")
    core.cmd(f"{iptables} -A FORWARD -s 10.0.10.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{iptables} -A FORWARD -s 10.0.20.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{iptables} -A FORWARD -s 10.0.30.0/24 -d 10.0.50.0/24 -j DROP")
    core.cmd(f"{iptables} -A FORWARD -d 10.0.50.0/24 -j DROP")

    core.cmd(f"{iptables} -A FORWARD -s 10.0.40.0/24 -d 10.0.60.0/24 -j ACCEPT")
    core.cmd(f"{iptables} -A FORWARD -s 10.0.10.0/24 -d 10.0.60.0/24 -j DROP")
    core.cmd(f"{iptables} -A FORWARD -s 10.0.20.0/24 -d 10.0.60.0/24 -j DROP")
    core.cmd(f"{iptables} -A FORWARD -s 10.0.30.0/24 -d 10.0.60.0/24 -j DROP")
    core.cmd(f"{iptables} -A FORWARD -d 10.0.60.0/24 -j DROP")

    core.cmd(f"{iptables} -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT")
    info(core.cmd(f"{iptables} -vnL FORWARD --line-numbers"))


def configure_vpn(net):
    """Configure OpenVPN static-key tunnel between vpn and ex."""
    info("*** Configuring VPN\n")

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

    openvpn = vpn.cmd("command -v openvpn").strip()
    if not openvpn:
        info("!!! Missing openvpn; install it with: sudo apt install openvpn. Skipping tunnel startup.\n")
        return False

    iptables = require_cmd(vpn, "iptables", "install it with: sudo apt install iptables")
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

    vpn.cmd(f"{iptables} -F")
    vpn.cmd(f"{iptables} -t nat -F")
    vpn.cmd(f"{iptables} -P FORWARD ACCEPT")
    vpn.cmd(f"{iptables} -t nat -A POSTROUTING -s 10.8.0.0/24 -d 10.0.0.0/16 -o vpn-eth1 -j MASQUERADE")
    vpn.cmd(f"{iptables} -A FORWARD -i tun0 -o vpn-eth1 -s 10.8.0.0/24 -d 10.0.0.0/16 -j ACCEPT")
    vpn.cmd(f"{iptables} -A FORWARD -i vpn-eth1 -o tun0 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT")

    vpn.cmd("openvpn --config /tmp/openvpn-server.conf --daemon --log /tmp/openvpn-server.log")
    time.sleep(1)
    ex.cmd("openvpn --config /tmp/openvpn-client.conf --daemon --log /tmp/openvpn-client.log")
    time.sleep(3)
    return True


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


def test_connectivity(net, vpn_enabled):
    """Run basic connectivity checks."""
    info("*** Testing connectivity\n")

    d1 = net.get("d1")
    o1 = net.get("o1")
    ex = net.get("ex")

    result = d1.cmd("ping -c 2 -W 1 10.0.10.2")
    info(f"Dorm d1 -> d2: {'success' if '0% packet loss' in result else 'failed'}\n")

    result = d1.cmd("ping -c 2 -W 1 10.0.20.1")
    info(f"Dorm -> teaching: {'success' if '0% packet loss' in result else 'failed'}\n")

    result = d1.cmd("curl -s --connect-timeout 2 http://10.0.100.10")
    info(f"Dorm -> Web: {'success' if 'Campus Web Server' in result else 'failed'}\n")

    result = d1.cmd("ping -c 2 -W 1 10.0.50.1")
    blocked = "100% packet loss" in result or "0 received" in result
    info(f"Dorm -> HR: {'blocked as expected' if blocked else 'unexpectedly allowed'}\n")

    result = d1.cmd("ping fn1")
    blocked = "100% packet loss" in result or "0 received" in result
    info(f"Dorm -> Finance: {'blocked as expected' if blocked else 'unexpectedly allowed'}\n")

    result = o1.cmd("ping -c 2 -W 1 10.0.50.1")
    info(f"Office -> HR: {'success' if '0% packet loss' in result else 'failed'}\n")

    result = ex.cmd("ping -c 2 -W 1 203.0.113.1")
    info(f"External ex -> VPN public IP: {'success' if '0% packet loss' in result else 'failed'}\n")

    if vpn_enabled:
        result = ex.cmd("ping -c 2 -W 2 10.8.0.1")
        info(f"External ex -> VPN tunnel: {'success' if '0% packet loss' in result else 'failed'}\n")

        result = ex.cmd("curl -s --connect-timeout 3 http://10.0.100.10")
        info(f"External ex via VPN -> Web: {'success' if 'Campus Web Server' in result else 'failed'}\n")
    else:
        info("External ex -> VPN tunnel: skipped because openvpn is not installed\n")


def run():
    """Run the topology."""
    setLogLevel("info")

    info("*** Creating campus router VPN topology\n")
    topo = CampusNetworkRouterVpnTopo()

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
        configure_l2_switches(net)
        configure_routing(net)
        configure_acl(net)
        start_services(net)
        vpn_enabled = configure_vpn(net)
        test_connectivity(net, vpn_enabled)

        info("*** Entering Mininet CLI\n")
        info("  exit\n\n")

        CLI(net)

    except KeyboardInterrupt:
        info("\n*** Interrupted\n")
    finally:
        info("*** Stopping network\n")
        net.stop()


if __name__ == "__main__":
    run()
