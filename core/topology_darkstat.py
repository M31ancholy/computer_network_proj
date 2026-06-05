#!/usr/bin/env python3
"""
Campus network topology with VPN access and Darkstat monitoring.

This variant reuses topology_vpn.py and starts Darkstat inside the core
router namespace to monitor all traffic visible on c.
"""

import time

from mininet.cli import CLI
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import OVSController, OVSKernelSwitch
from mininet.util import dumpNodeConnections

from topology_vpn import (
    CampusNetworkRouterVpnTopo,
    configure_acl,
    configure_l2_switches,
    configure_routing,
    configure_vpn,
    start_services,
    test_connectivity,
)


def start_core_darkstat_monitor(net):
    """Start Darkstat on the core router namespace."""
    info("*** Starting core router traffic monitor (darkstat)\n")

    core = net.get("c")
    darkstat = core.cmd("command -v darkstat").strip()
    log_path = "/tmp/mininet-core-darkstat.log"
    pid_path = "/tmp/mininet-core-darkstat.pid"

    if not darkstat:
        info("!!! Missing darkstat; install it with: sudo apt install darkstat\n")
        return False

    core.cmd(
        f"if [ -f {pid_path} ]; then "
        f"darkstat_pid=$(cat {pid_path}); "
        f'if pgrep -a darkstat | grep -q "^$darkstat_pid "; then '
        "kill \"$darkstat_pid\" || true; "
        "fi; "
        f"rm -f {pid_path}; "
        "fi"
    )
    core.cmd(f"rm -f {log_path}")
    core.cmd(
        f"{darkstat} -i any -b 0.0.0.0 -p 3001 --no-daemon "
        f"> {log_path} 2>&1 & echo $! > {pid_path}"
    )
    time.sleep(1)

    if "-p 3001" not in core.cmd("pgrep -a darkstat || true"):
        info(f"!!! darkstat did not start; check from Mininet CLI: c cat {log_path}\n")
        return False

    info("darkstat core router is monitoring: any\n")
    info("darkstat core router web UI listens on port 3001\n")
    info("From Mininet CLI, test with: d1 curl http://10.0.10.254:3001\n")
    info("To open Darkstat from the host browser, run in another terminal:\n")
    info("  sudo ip addr add 10.0.10.253/24 dev ds 2>/dev/null || true\n")
    info("  sudo ip link set ds up\n")
    info("Then browse: http://10.0.10.254:3001\n")
    return True


def run():
    """Run the topology."""
    setLogLevel("info")

    info("*** Creating campus router VPN topology with Darkstat\n")
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
        start_core_darkstat_monitor(net)
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
