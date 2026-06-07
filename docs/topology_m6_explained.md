# `core/topology_m6.py` 汇报讲解稿

这份文档用于讲解 `core/topology_m6.py`。它不是简单翻译代码，而是按汇报时容易说明白的顺序，把代码、网络概念和验证方法串起来。

## 1. 这个文件整体在做什么

`topology_m6.py` 是一个基于 Mininet 的校园网仿真实验脚本。

它模拟了一个双校区校园网络：

- A 校区接在交换机 `s1` 上，使用 `10.0.x.x` 网段。
- B 校区接在交换机 `s2` 上，使用 `10.1.x.x` 网段。
- 核心路由器叫 `c`，负责 VLAN 间路由、校区间路由、ACL 访问控制和 DHCP 服务。
- 互联网/VPN 模拟区域接在交换机 `is` 上。
- 普通终端主机不再手动写死 IP，而是通过 DHCP 动态获取 IP。
- 服务器 `ws`、`fs` 和 VPN 相关节点 `vpn`、`ex` 保持静态 IP。

M6 相比 M5 的核心新增点是 DHCP：

- 在核心路由器 `c` 的每个普通 VLAN 子接口上启动一个 `dnsmasq` DHCP 服务。
- 在普通主机上启动 `dhcpcd` DHCP 客户端。
- 主机拿到的 IP 会落在各 VLAN 的 `.50` 到 `.150` 范围内。
- 默认网关也由 DHCP 下发给主机。

一句话总结：

> 这个脚本用 Mininet 搭了一个双校区、多个 VLAN、单臂路由、带 DHCP 自动分配地址和 ACL 访问控制的校园网络。

## 2. 先理解几个关键网络概念

### 2.1 Mininet 是什么

Mininet 是一个网络仿真工具。它可以在一台 Linux 机器上创建虚拟主机、虚拟交换机、虚拟链路，让我们像操作真实网络设备一样测试网络拓扑。

在代码里：

- `addHost()` 创建虚拟主机或路由器。
- `addSwitch()` 创建虚拟交换机。
- `addLink()` 创建链路。
- `CLI(net)` 进入 Mininet 命令行，可以手动执行 `ping`、`ip addr`、`curl` 等命令。

### 2.2 VLAN 是什么

VLAN 是虚拟局域网。它的作用是把同一个物理交换机上的设备逻辑隔离成多个二层网络。

比如 A 校区：

- VLAN 10：宿舍
- VLAN 20：教学楼
- VLAN 30：图书馆
- VLAN 40：办公楼
- VLAN 50：人事处
- VLAN 60：财务处
- VLAN 100：服务器区
- VLAN 200：VPN 内网区

即使这些主机都接在交换机 `s1` 上，只要端口属于不同 VLAN，它们在二层上就是隔离的。

### 2.3 Access 端口和 Trunk 端口

交换机端口在 VLAN 里常见两种角色：

Access 端口：

- 面向普通主机。
- 一个 access 端口只属于一个 VLAN。
- 主机发出的普通以太网帧没有 VLAN 标签。
- 交换机在这个端口上自动把流量归入指定 VLAN。

Trunk 端口：

- 面向交换机、路由器等网络设备。
- 一个 trunk 端口可以承载多个 VLAN 的流量。
- 流量通过 802.1Q 标签区分属于哪个 VLAN。

在这个脚本里：

- `s1` 连接普通 A 校区主机的端口是 access 端口。
- `s2` 连接普通 B 校区主机的端口是 access 端口。
- `s1-eth1 <-> c-eth0` 是 A 校区 trunk。
- `s2-eth1 <-> c-eth2` 是 B 校区 trunk。

### 2.4 单臂路由是什么

单臂路由，也叫 Router-on-a-Stick。它的意思是：路由器只用一根物理链路连接交换机，但是这根链路是 trunk，可以承载多个 VLAN。

路由器在同一块物理网卡上创建多个 VLAN 子接口：

- `c-eth0.10` 服务 A 校区 VLAN 10。
- `c-eth0.20` 服务 A 校区 VLAN 20。
- `c-eth0.30` 服务 A 校区 VLAN 30。
- `c-eth2.10` 服务 B 校区 VLAN 10。
- `c-eth2.20` 服务 B 校区 VLAN 20。

每个子接口都有自己的 IP。这个 IP 就是对应 VLAN 的网关。

### 2.5 网关是什么

网关通常指默认网关，也就是主机离开自己网段时要交给的下一跳设备。

例如 `ad1` 是 A 校区宿舍主机，假设它通过 DHCP 拿到：

- IP：`10.0.10.50/24`
- 默认网关：`10.0.10.254`

那么：

- `ad1` 访问 `10.0.10.60`：同网段，直接二层通信，不需要网关。
- `ad1` 访问 `10.0.20.50`：不同网段，要把包交给 `10.0.10.254`。
- `ad1` 访问 `10.1.10.50`：不同校区，也要先交给 `10.0.10.254`。

在本项目中，所有 VLAN 的网关都在核心路由器 `c` 上：

| VLAN | 网段 | 网关子接口 | 网关 IP |
|---|---|---|---|
| A-Dorm 10 | `10.0.10.0/24` | `c-eth0.10` | `10.0.10.254` |
| A-Teaching 20 | `10.0.20.0/24` | `c-eth0.20` | `10.0.20.254` |
| A-Library 30 | `10.0.30.0/24` | `c-eth0.30` | `10.0.30.254` |
| A-Office 40 | `10.0.40.0/24` | `c-eth0.40` | `10.0.40.254` |
| A-HR 50 | `10.0.50.0/24` | `c-eth0.50` | `10.0.50.254` |
| A-Finance 60 | `10.0.60.0/24` | `c-eth0.60` | `10.0.60.254` |
| A-Server 100 | `10.0.100.0/24` | `c-eth0.100` | `10.0.100.254` |
| A-VPN 200 | `10.0.200.0/24` | `c-eth0.200` | `10.0.200.254` |
| B-Dorm 10 | `10.1.10.0/24` | `c-eth2.10` | `10.1.10.254` |
| B-Teaching 20 | `10.1.20.0/24` | `c-eth2.20` | `10.1.20.254` |
| B-Library 30 | `10.1.30.0/24` | `c-eth2.30` | `10.1.30.254` |
| B-Office 40 | `10.1.40.0/24` | `c-eth2.40` | `10.1.40.254` |

### 2.6 DHCP 是什么

DHCP 用来自动给主机分配网络配置。主机启动后，不需要手动配置 IP，而是向网络中广播请求：

1. 客户端发送 DHCP Discover：有没有 DHCP 服务器？
2. 服务器发送 DHCP Offer：我可以给你这个 IP。
3. 客户端发送 DHCP Request：我要用这个 IP。
4. 服务器发送 DHCP Ack：确认租约生效。

本脚本中：

- DHCP 服务器程序是 `dnsmasq`。
- DHCP 客户端程序是 `dhcpcd`。
- 每个需要 DHCP 的 VLAN 子接口上启动一个 `dnsmasq`。
- 每个普通终端主机启动一个 `dhcpcd`。

为什么每个 VLAN 子接口要有独立 DHCP 服务？

因为 VLAN 是二层隔离的。VLAN 10 的 DHCP 广播不会自然跑到 VLAN 20。每个 VLAN 都需要能在自己的广播域里收到 DHCP 响应，所以脚本让 `dnsmasq` 绑定在对应的子接口上。

## 3. 文件开头：导入模块

```python
import re
import time

from mininet.cli import CLI
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import OVSController, OVSKernelSwitch
from mininet.topo import Topo
from mininet.util import dumpNodeConnections

from linux_router import LinuxRouter
```

这些导入分别用于：

- `re`：用正则表达式从 `ip addr` 命令输出中提取 IP 地址。
- `time`：等待 DHCP 服务启动、等待主机获取租约。
- `CLI`：启动 Mininet 交互命令行。
- `info`、`setLogLevel`：输出日志。
- `Mininet`：创建整个仿真网络。
- `OVSController`、`OVSKernelSwitch`：使用 Open vSwitch 交换机。
- `Topo`：定义网络拓扑的基类。
- `dumpNodeConnections`：打印节点连接关系，方便调试。
- `LinuxRouter`：项目自定义的 Linux 路由器节点，会开启 IP 转发。

`LinuxRouter` 在 `core/linux_router.py` 中定义，核心作用是执行：

```bash
sysctl -w net.ipv4.ip_forward=1
```

这表示让 Linux 主机具备三层转发能力。普通 Linux 主机默认不转发别人的 IP 包，开启这个开关后，节点 `c` 才能当路由器。

## 4. VLAN 规划表

### 4.1 `CAMPUS_A_VLANS`

```python
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
```

这是 A 校区的 VLAN 规划。

字典的 key 是 VLAN ID，比如 `10`、`20`、`100`。

value 是一个二元组：

- 第一个值是描述，比如 `"A-Dorm"`。
- 第二个值是网关 IP 和掩码，比如 `"10.0.10.254/24"`。

后面 `configure_vlan_routing()` 会遍历这个表，在核心路由器 `c` 上创建：

- `c-eth0.10`
- `c-eth0.20`
- `c-eth0.30`
- `c-eth0.40`
- `c-eth0.50`
- `c-eth0.60`
- `c-eth0.100`
- `c-eth0.200`

这些子接口分别服务 A 校区不同 VLAN。

### 4.2 `CAMPUS_B_VLANS`

```python
CAMPUS_B_VLANS = {
    10:  ("B-Dorm",     "10.1.10.254/24"),
    20:  ("B-Teaching", "10.1.20.254/24"),
    30:  ("B-Library",  "10.1.30.254/24"),
    40:  ("B-Office",   "10.1.40.254/24"),
}
```

这是 B 校区的 VLAN 规划。

B 校区也有 VLAN 10、20、30、40，但网段是 `10.1.x.x`，并且走 `c-eth2` 这条 trunk。

这里有一个容易混淆的点：

> A 校区和 B 校区都可以有 VLAN 10，因为它们在不同 trunk 接口上：A 是 `c-eth0.10`，B 是 `c-eth2.10`。

同样的 VLAN ID 不代表一定是同一个二层网络。它还取决于所在的交换机和 trunk 链路。

### 4.3 `HOST_SWITCH_VLAN`

```python
HOST_SWITCH_VLAN = {
    "ad1": ("s1", 10), "ad2": ("s1", 10), "ad3": ("s1", 10),
    "at1": ("s1", 20), "at2": ("s1", 20),
    ...
    "bd1": ("s2", 10), "bd2": ("s2", 10),
    ...
}
```

这个表表示每台主机接在哪台交换机、属于哪个 VLAN。

例如：

- `"ad1": ("s1", 10)` 表示 `ad1` 接在 A 校区交换机 `s1` 上，属于 VLAN 10。
- `"ws": ("s1", 100)` 表示 Web 服务器接在 `s1` 上，属于服务器 VLAN 100。
- `"vpn": ("s1", 200)` 表示 VPN 服务器的内网侧接在 `s1` 上，属于 VLAN 200。
- `"bo1": ("s2", 40)` 表示 B 校区办公楼主机 `bo1` 接在 `s2` 上，属于 VLAN 40。

这个表主要供 `configure_switches()` 使用。函数会根据这个表找到交换机上连接主机的端口，然后执行：

```bash
ovs-vsctl set port <port> tag=<vlan_id>
```

这就把交换机端口设置成指定 VLAN 的 access 端口。

## 5. DHCP 相关配置表

### 5.1 `DHCP_RANGES`

```python
DHCP_RANGES = {
    "c-eth0.10":  ("10.0.10.50",  "10.0.10.150",  "10.0.10.254",  "12h"),
    ...
    "c-eth2.40":  ("10.1.40.50",  "10.1.40.150",  "10.1.40.254",  "12h"),
}
```

这个表定义 DHCP 服务器应该在哪些接口上启动，以及每个接口分配什么地址池。

key 是 VLAN 子接口名，比如：

- `c-eth0.10`
- `c-eth0.20`
- `c-eth2.10`
- `c-eth2.40`

value 是四个值：

1. DHCP 地址池起始 IP。
2. DHCP 地址池结束 IP。
3. 默认网关 IP。
4. 租约时间。

例如：

```python
"c-eth0.10": ("10.0.10.50", "10.0.10.150", "10.0.10.254", "12h")
```

意思是：

- 在 A 校区宿舍 VLAN 的网关接口 `c-eth0.10` 上启动 DHCP。
- 可以分配 `10.0.10.50` 到 `10.0.10.150`。
- 告诉客户端默认网关是 `10.0.10.254`。
- 租约时间是 12 小时。

注意：VLAN 100 和 VLAN 200 没有写进 `DHCP_RANGES`。

原因：

- VLAN 100 是服务器区，`ws`、`fs` 需要固定 IP，方便别人访问。
- VLAN 200 是 VPN 内网区，`vpn` 也需要固定 IP，保证路由和 VPN 配置稳定。

### 5.2 `DHCP_HOSTS`

```python
DHCP_HOSTS = [
    "ad1", "ad2", "ad3",
    "at1", "at2",
    ...
    "bo1", "bo2",
]
```

这个列表表示哪些主机要通过 DHCP 获取地址。

普通终端都在这里：

- A 校区宿舍、教学楼、图书馆、办公楼、人事处、财务处。
- B 校区宿舍、教学楼、图书馆、办公楼。

不在这里的节点保持静态：

- `ws`：Web 服务器。
- `fs`：FTP 服务器。
- `vpn`：VPN 服务器。
- `ex`：外部客户端。

## 6. 拓扑类 `DualCampusVlanTopo`

```python
class DualCampusVlanTopo(Topo):
```

这个类继承 Mininet 的 `Topo`，用于描述网络里有哪些节点、交换机和链路。

真正创建拓扑的是它的 `build()` 方法。

### 6.1 创建核心路由器

```python
core = self.addHost("c", cls=LinuxRouter, ip=None)
```

这行创建核心路由器 `c`。

关键点：

- `addHost()` 本来创建普通主机。
- `cls=LinuxRouter` 表示这个主机使用自定义路由器类。
- `ip=None` 表示先不让 Mininet 自动给它配置 IP，后面手动创建 VLAN 子接口并配置 IP。

### 6.2 创建三个交换机

```python
s1  = self.addSwitch("s1",  dpid="0000000000000001")
is_ = self.addSwitch("is",  dpid="0000000000000300")
s2  = self.addSwitch("s2",  dpid="0000000000000002")
```

这三行创建三个 Open vSwitch 交换机：

- `s1`：A 校区交换机。
- `s2`：B 校区交换机。
- `is`：互联网/VPN 模拟交换机。

变量名用 `is_` 是因为 `is` 是 Python 关键字，不能直接当变量名。

`dpid` 是交换机的数据路径 ID，相当于交换机在 SDN/OVS 里的唯一编号。

### 6.3 创建核心链路

```python
self.addLink(s1,  core)
self.addLink(is_, core)
self.addLink(s2,  core)
```

这三条链路非常重要，因为创建顺序决定 `c` 上的网卡编号：

1. `s1 <-> c` 创建后，核心路由器侧是 `c-eth0`，作为 A 校区 trunk。
2. `is <-> c` 创建后，核心路由器侧是 `c-eth1`，作为互联网/VPN 侧接口。
3. `s2 <-> c` 创建后，核心路由器侧是 `c-eth2`，作为 B 校区 trunk。

所以后面的 VLAN 子接口才会写成：

- A 校区：`c-eth0.<vlan_id>`
- B 校区：`c-eth2.<vlan_id>`

### 6.4 创建 A 校区 DHCP 主机

以 A 校区宿舍为例：

```python
for i in range(1, 4):
    h = self.addHost(
        f"ad{i}",
        ip="0.0.0.0",
        mac=f"00:00:00:00:10:0{i}",
    )
    self.addLink(h, s1)
```

这段创建：

- `ad1`
- `ad2`
- `ad3`

它们都连接到 `s1`。

`ip="0.0.0.0"` 的意思不是最终 IP，而是占位。后面会通过 DHCP 获取真正 IP。

`mac` 是手动指定的 MAC 地址。这样做有两个好处：

- 地址稳定，便于调试。
- DHCP 分配时客户端身份稳定。

其他 A 校区普通主机也是同样逻辑：

- `at1`、`at2`：教学楼，VLAN 20。
- `al1`：图书馆，VLAN 30。
- `ao1`、`ao2`：办公楼，VLAN 40。
- `ahr1`、`ahr2`：人事处，VLAN 50。
- `afn1`、`afn2`：财务处，VLAN 60。

这些主机创建时都没有默认路由，因为默认网关会由 DHCP 下发。

### 6.5 创建服务器区静态主机

```python
ws = self.addHost(
    "ws",
    ip="10.0.100.10/24",
    mac="00:00:00:00:64:01",
    defaultRoute="via 10.0.100.254",
)
```

`ws` 是 Web 服务器。

它使用静态 IP：

- IP：`10.0.100.10/24`
- 网关：`10.0.100.254`
- VLAN：100

为什么服务器要静态 IP？

因为客户端要访问服务器，如果服务器 IP 每次启动都变，会很难配置和验证。服务器通常要有固定地址。

`fs` 是 FTP 服务器：

```python
fs = self.addHost(
    "fs",
    ip="10.0.100.20/24",
    mac="00:00:00:00:64:02",
    defaultRoute="via 10.0.100.254",
)
```

它使用：

- IP：`10.0.100.20/24`
- 网关：`10.0.100.254`
- VLAN：100

### 6.6 创建 VPN 服务器和外部客户端

```python
vpn = self.addHost("vpn", ip=None)
self.addLink(vpn, s1)
self.addLink(vpn, is_)
```

`vpn` 有两块网卡：

- `vpn-eth0` 连到 A 校区交换机 `s1`，后面被划入 VLAN 200。
- `vpn-eth1` 连到互联网交换机 `is`。

这模拟 VPN 服务器一边连校园内网，一边连外部网络。

外部客户端：

```python
ex = self.addHost(
    "ex",
    ip="203.0.113.2/24",
    defaultRoute="via 203.0.113.1",
)
self.addLink(ex, is_)
```

`ex` 模拟互联网用户，静态 IP 是 `203.0.113.2/24`，默认网关是 VPN 服务器公网侧 `203.0.113.1`。

### 6.7 创建 B 校区 DHCP 主机

B 校区普通主机和 A 校区类似，只是连接到 `s2`，MAC 地址也换成 `00:00:00:01:...`，网段是 `10.1.x.x`。

例如：

```python
for i in range(1, 3):
    h = self.addHost(
        f"bd{i}",
        ip="0.0.0.0",
        mac=f"00:00:00:01:10:0{i}",
    )
    self.addLink(h, s2)
```

这段创建 B 校区宿舍主机 `bd1`、`bd2`，后续通过 DHCP 从 `10.1.10.50-10.1.10.150` 获取 IP。

## 7. `configure_switches(net)`：配置交换机和 VLAN access 端口

这个函数做两件事：

1. 把 OVS 交换机设为普通交换机工作模式。
2. 给连接主机的端口打 VLAN access tag。

### 7.1 设置 standalone 和 NORMAL 转发

```python
for sw_name in ["s1", "s2", "is"]:
    sw = net.get(sw_name)
    sw.cmd(f"ovs-vsctl set-fail-mode {sw_name} standalone")
    sw.cmd(f"ovs-ofctl add-flow {sw_name} priority=0,actions=NORMAL")
```

`net.get(sw_name)` 从 Mininet 网络中拿到对应交换机对象。

`set-fail-mode standalone` 表示即使没有外部控制器，交换机也能像普通二层交换机一样工作。

`ovs-ofctl add-flow ... actions=NORMAL` 添加一条默认流表，让 OVS 使用普通交换机的学习转发逻辑。

简单说：

> 这几行让 OVS 不依赖复杂 SDN 控制器，而是按传统交换机方式转发。

### 7.2 给主机端口设置 VLAN tag

```python
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
```

这段逻辑可以分成几步理解：

1. 遍历 `HOST_SWITCH_VLAN`，知道每台主机应该属于哪个 VLAN。
2. 找到这台主机对象和交换机对象。
3. 遍历主机的接口，找到它连接到交换机的那条链路。
4. 找到链路另一端在交换机上的端口。
5. 对交换机端口执行 `ovs-vsctl set port ... tag=...`。

例如 `ad1` 接到 `s1` 的某个端口，脚本会把这个端口设置为 VLAN 10 的 access 端口。

`trunk` 端口没有设置 tag：

```python
info("  s1-eth1 -> c-eth0 (trunk, A-campus all VLANs)\n")
info("  s2-eth1 -> c-eth2 (trunk, B-campus all VLANs)\n")
```

在 OVS 中，不设置 access tag 的端口可以作为 trunk 使用，承载多个 VLAN 的 802.1Q 标记流量。

## 8. `configure_vlan_routing(net)`：在路由器上创建 VLAN 子接口

这个函数是单臂路由的核心。

### 8.1 开启 IP 转发和 VLAN 支持

```python
core = net.get("c")
core.cmd("sysctl -w net.ipv4.ip_forward=1")
core.cmd("modprobe 8021q")
```

`net.get("c")` 获取核心路由器。

`ip_forward=1` 表示开启三层转发。

`modprobe 8021q` 加载 Linux 的 802.1Q VLAN 模块。没有这个模块就无法创建 `c-eth0.10` 这种 VLAN 子接口。

### 8.2 配置 A 校区 trunk：`c-eth0`

```python
core.cmd("ip addr flush dev c-eth0")
core.cmd("ip link set c-eth0 up")
for vlan_id, (desc, gw_ip) in CAMPUS_A_VLANS.items():
    subif = f"c-eth0.{vlan_id}"
    core.cmd(f"ip link add link c-eth0 name {subif} type vlan id {vlan_id}")
    core.cmd(f"ip addr add {gw_ip} dev {subif}")
    core.cmd(f"ip link set {subif} up")
```

逐行解释：

- `ip addr flush dev c-eth0`：清空物理接口上的旧 IP，避免和子接口冲突。
- `ip link set c-eth0 up`：启用物理接口。
- 遍历 A 校区 VLAN 表。
- `subif = f"c-eth0.{vlan_id}"`：生成子接口名，比如 `c-eth0.10`。
- `ip link add link c-eth0 name c-eth0.10 type vlan id 10`：基于物理接口创建 VLAN 子接口。
- `ip addr add 10.0.10.254/24 dev c-eth0.10`：给子接口配置网关 IP。
- `ip link set c-eth0.10 up`：启用子接口。

这一步之后，核心路由器 `c` 就拥有了多个 A 校区网关接口。

### 8.3 配置互联网/VPN 接口：`c-eth1`

```python
core.cmd("ip addr flush dev c-eth1")
core.cmd("ip link set c-eth1 up")
```

`c-eth1` 连接 `is`，不参与 VLAN trunk，所以这里仅清空并启用接口。

注意：这个文件里没有给 `c-eth1` 配 IP。公网侧 IP 配在 `vpn-eth1` 和 `ex-eth0` 上，`c-eth1` 只是连接在同一个模拟互联网交换机上。

### 8.4 配置 B 校区 trunk：`c-eth2`

```python
core.cmd("ip addr flush dev c-eth2")
core.cmd("ip link set c-eth2 up")
for vlan_id, (desc, gw_ip) in CAMPUS_B_VLANS.items():
    subif = f"c-eth2.{vlan_id}"
    core.cmd(f"ip link add link c-eth2 name {subif} type vlan id {vlan_id}")
    core.cmd(f"ip addr add {gw_ip} dev {subif}")
    core.cmd(f"ip link set {subif} up")
```

逻辑和 A 校区一样，只是物理接口从 `c-eth0` 换成 `c-eth2`，网段从 `10.0.x.x` 换成 `10.1.x.x`。

### 8.5 验证 VLAN 子接口

```python
result = core.cmd("ip -d link show type vlan 2>/dev/null | grep -E 'c-eth[02]\\.'")
info("VLAN sub-interfaces:\n" + result + "\n")
```

这条命令在路由器上查看所有 VLAN 类型的接口，只显示 `c-eth0.*` 和 `c-eth2.*`。

如果看到 `c-eth0.10`、`c-eth0.20`、`c-eth2.10` 等，就说明 VLAN 子接口创建成功。

## 9. `start_dhcp_servers(net)`：启动 DHCP 服务器

这是 M6 的核心新增函数。

它在核心路由器 `c` 上，为每个需要 DHCP 的 VLAN 子接口启动一个 `dnsmasq` 进程。

### 9.1 获取核心路由器并清理旧状态

```python
core = net.get("c")
core.cmd("pkill -f 'keep-in-foreground' 2>/dev/null || true")
core.cmd("rm -f /tmp/m6-dhcp-*.leases /tmp/m6-dhcp-*.pid /tmp/m6-dhcp-*.log")
```

作用：

- 杀掉上次残留的 `dnsmasq`。
- 删除旧租约文件、pid 文件和日志文件。

`|| true` 是为了即使没有进程可杀也不报错影响后续执行。

### 9.2 清除旧的 `dhcpcd` lease

```python
import glob as _glob
for f in _glob.glob("/var/lib/dhcpcd/*.lease"):
    try:
        import os as _os
        _os.remove(f)
    except OSError:
        pass
```

这里删除宿主机文件系统里的旧 DHCP 租约文件。

为什么要删？

因为 Mininet 的各个网络 namespace 共享同一个文件系统。如果保留旧 lease，`dhcpcd` 可能尝试复用旧地址，导致获取 IP 变慢或出现异常。

### 9.3 检查 `dnsmasq` 是否安装

```python
dnsmasq = core.cmd("command -v dnsmasq").strip()
if not dnsmasq:
    info("!!! dnsmasq not found; install with: sudo apt install dnsmasq\n")
    return False
```

`command -v dnsmasq` 用来查找 `dnsmasq` 程序路径。

如果系统没安装，就打印提示并返回 `False`。

### 9.4 为每个 VLAN 子接口启动一个 DHCP 服务

```python
for subif, (start, end, gw, lease) in DHCP_RANGES.items():
    safe = subif.replace("-", "_").replace(".", "_")
    lf   = f"/tmp/m6-dhcp-{safe}.leases"
    pf   = f"/tmp/m6-dhcp-{safe}.pid"
    log  = f"/tmp/m6-dhcp-{safe}.log"
```

这里遍历 `DHCP_RANGES`。

`safe` 是把接口名转换成适合做文件名的形式：

- `c-eth0.10` 变成 `c_eth0_10`

然后生成：

- lease 文件：`/tmp/m6-dhcp-c_eth0_10.leases`
- pid 文件：`/tmp/m6-dhcp-c_eth0_10.pid`
- 日志文件：`/tmp/m6-dhcp-c_eth0_10.log`

### 9.5 `dnsmasq` 启动命令

```python
cmd = (
    f"{dnsmasq}"
    f" --keep-in-foreground"
    f" --no-ping"
    f" --interface={subif}"
    f" --bind-interfaces"
    f" --port=0"
    f" --dhcp-range={start},{end},{lease}"
    f" --dhcp-option=3,{gw}"
    f" --dhcp-leasefile={lf}"
    f" --pid-file={pf}"
    f" --log-facility=-"
    f" > {log} 2>&1 &"
)
core.cmd(cmd)
```

这些参数很重要：

- `--keep-in-foreground`：让 `dnsmasq` 不自己变成后台守护进程。脚本再用 `&` 把它放到后台。这样它会留在 Mininet 节点 `c` 的 network namespace 里。
- `--no-ping`：分配地址前不先 ping 地址。实验环境里可以加快分配速度。
- `--interface=<subif>`：只监听某个 VLAN 子接口，比如 `c-eth0.10`。
- `--bind-interfaces`：严格绑定指定接口，避免跨 VLAN 响应 DHCP。
- `--port=0`：关闭 DNS 功能，只提供 DHCP。
- `--dhcp-range=<start>,<end>,<lease>`：设置地址池和租约时间。
- `--dhcp-option=3,<gw>`：DHCP Option 3 是默认路由器，也就是默认网关。
- `--dhcp-leasefile=<lf>`：保存租约信息。
- `--pid-file=<pf>`：每个 DHCP 实例使用独立 pid 文件。
- `--log-facility=-`：日志输出到标准错误，再被重定向到日志文件。
- `> {log} 2>&1 &`：把日志写入文件，并在后台运行。

这里最关键的网络逻辑是：

> 每个 VLAN 子接口只服务自己的 VLAN，给客户端分配同网段 IP，并下发该 VLAN 的网关。

### 9.6 验证 DHCP 服务数量

```python
time.sleep(0.5)
count = core.cmd("pgrep -c -f 'keep-in-foreground' 2>/dev/null || echo 0").strip()
info(f"  {count} dnsmasq instance(s) running in router c namespace\n")
return True
```

等待半秒，让 `dnsmasq` 完成端口绑定。

然后用 `pgrep` 统计正在运行的 `dnsmasq` 实例数量。

本脚本里 `DHCP_RANGES` 有 10 个接口，所以正常应该看到 10 个实例。

## 10. `configure_dhcp_clients(net)`：启动 DHCP 客户端

这个函数让普通终端主机通过 DHCP 获取 IP。

### 10.1 删除旧 lease

```python
for hname in DHCP_HOSTS:
    intf = f"{hname}-eth0"
    lease = f"/var/lib/dhcpcd/{intf}.lease"
    import os
    try:
        os.remove(lease)
        info(f"  removed stale lease: {lease}\n")
    except FileNotFoundError:
        pass
```

每台主机的默认接口一般是 `<主机名>-eth0`，例如：

- `ad1-eth0`
- `bd1-eth0`

这段删除对应接口的旧 lease 文件，避免 DHCP 客户端复用旧地址。

### 10.2 清空接口并启动 `dhcpcd`

```python
for hname in DHCP_HOSTS:
    h    = net.get(hname)
    intf = f"{hname}-eth0"
    h.cmd(f"ip addr flush dev {intf}")
    h.cmd(f"ip link set {intf} up")
    h.cmd(f"dhcpcd -B -t 15 {intf} > /tmp/m6-dhcpcd-{hname}.log 2>&1 &")
    info(f"  dhcpcd started on {hname} ({intf})\n")
```

逐行说明：

- `net.get(hname)` 获取主机对象。
- `ip addr flush dev <intf>` 清空接口上的占位 IP。
- `ip link set <intf> up` 启用接口。
- `dhcpcd -B -t 15 <intf>` 启动 DHCP 客户端。

`dhcpcd` 参数：

- `-B`：不让 `dhcpcd` 自己后台化。
- `-t 15`：最多等待 15 秒获取租约。
- `&`：由 shell 把进程放到后台运行。

这里和 `dnsmasq` 一样，重点是让进程留在对应 Mininet 主机自己的 network namespace 里。

### 10.3 轮询等待所有主机拿到 IP

```python
deadline = time.time() + 30
while time.time() < deadline:
    time.sleep(2)
    missing = []
    for hname in DHCP_HOSTS:
        h   = net.get(hname)
        out = h.cmd(f"ip -4 addr show dev {hname}-eth0 2>/dev/null")
        m   = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", out)
        if not m:
            missing.append(hname)
    if not missing:
        info("  All hosts obtained DHCP leases.\n")
        break
    info(f"  Still waiting: {', '.join(missing)}\n")
else:
    info("  [WARN] Timeout: some hosts may not have obtained IP\n")
```

这段最多等待 30 秒。

每 2 秒检查一次每台 DHCP 主机是否已经有 IPv4 地址。

正则：

```python
r"inet (\d+\.\d+\.\d+\.\d+)/"
```

用于从 `ip addr` 输出里提取 IP，比如 `10.0.10.50`。

如果全部主机都有 IP，就提前结束等待。

### 10.4 打印 DHCP 获取结果

```python
for hname in DHCP_HOSTS:
    h   = net.get(hname)
    out = h.cmd(f"ip -4 addr show dev {hname}-eth0 2>/dev/null")
    m   = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", out)
    ip  = m.group(1) if m else "NO IP"
    gw  = h.cmd("ip route show default 2>/dev/null").strip()
    info(f"  {hname:6s}  ip={ip:15s}  {gw}\n")
```

这会打印每台主机拿到的 IP 和默认路由。

汇报时可以说：

> DHCP 不只是分配 IP，还会把默认网关通过 Option 3 下发给客户端，所以主机的 `ip route` 里会出现 `default via ...`。

## 11. `get_host_ip(node)`：动态读取主机 IP

```python
def get_host_ip(node):
    intf = f"{node.name}-eth0"
    out  = node.cmd(f"ip -4 addr show dev {intf} 2>/dev/null")
    m    = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", out)
    return m.group(1) if m else ""
```

因为 M6 的主机 IP 是 DHCP 动态分配的，不能像 M5 那样写死 `10.0.10.1`。

这个函数根据节点名推导接口名，然后执行：

```bash
ip -4 addr show dev ad1-eth0
```

再用正则提取 IPv4 地址。

如果找不到 IP，就返回空字符串。

后面的连通性测试会大量使用这个函数。

## 12. `configure_vpn_addresses(net)`：配置 VPN 和外部客户端地址

```python
vpn = net.get("vpn")
vpn.cmd("ip addr flush dev vpn-eth0")
vpn.cmd("ip addr add 10.0.200.10/24 dev vpn-eth0")
vpn.cmd("ip link set vpn-eth0 up")
vpn.cmd("ip route replace 10.0.0.0/8 via 10.0.200.254")
```

这段配置 VPN 服务器内网侧：

- `vpn-eth0` 在 VLAN 200。
- IP 是 `10.0.200.10/24`。
- 访问校园网 `10.0.0.0/8` 时，下一跳走 `10.0.200.254`，也就是核心路由器 VLAN 200 的网关。

```python
vpn.cmd("ip addr flush dev vpn-eth1")
vpn.cmd("ip addr add 203.0.113.1/24 dev vpn-eth1")
vpn.cmd("ip link set vpn-eth1 up")
```

这段配置 VPN 服务器公网侧：

- `vpn-eth1` 接到 `is`。
- IP 是 `203.0.113.1/24`。

```python
ex = net.get("ex")
ex.cmd("ip addr flush dev ex-eth0")
ex.cmd("ip addr add 203.0.113.2/24 dev ex-eth0")
ex.cmd("ip link set ex-eth0 up")
ex.cmd("ip route replace default via 203.0.113.1")
```

这段配置外部客户端：

- IP：`203.0.113.2/24`
- 默认网关：`203.0.113.1`

这里的 `203.0.113.0/24` 是文档示例地址段，常用于实验或说明，不是真实公网环境。

## 13. `start_services(net)`：启动 Web 和 FTP 服务

### 13.1 Web 服务

```python
ws = net.get("ws")
ws.cmd("mkdir -p /var/www/html")
ws.cmd('echo "<h1>Shared Campus Web Server</h1>" > /var/www/html/index.html')
ws.cmd("python3 -m http.server 80 --directory /var/www/html &>/dev/null &")
```

这段在 `ws` 上启动 Web 服务。

步骤：

1. 创建网页目录 `/var/www/html`。
2. 写入一个简单首页。
3. 用 Python 内置 HTTP 服务器监听 80 端口。

所以其他主机可以执行：

```bash
curl http://10.0.100.10
```

如果能返回 `Shared Campus Web Server`，说明访问服务器成功。

### 13.2 FTP 服务

```python
fs = net.get("fs")
fs.cmd("mkdir -p /var/ftp")
fs.cmd('echo "Shared Campus FTP" > /var/ftp/welcome.txt')
```

这段创建 FTP 根目录和欢迎文件。

后面的大段 Python 一行命令使用 `pyftpdlib` 启动 FTP 服务器：

```python
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer
```

它配置匿名访问 `/var/ftp`，监听 `0.0.0.0:21`。

`0.0.0.0` 表示监听本主机所有接口。

## 14. `configure_acl(net)`：配置访问控制规则

ACL 是访问控制列表。这个脚本通过 Linux `iptables` 的 `FORWARD` 链实现三层访问控制。

为什么用 `FORWARD` 链？

因为核心路由器 `c` 在转发别人的流量。比如 `ad1` 访问 `ahr1`，包不是发给 `c` 自己，而是经过 `c` 转发，所以匹配 `FORWARD`。

### 14.1 查找并初始化 `iptables`

```python
core = net.get("c")
ipt  = core.cmd("command -v iptables").strip()
if not ipt:
    info("!!! iptables not found; skipping ACL\n")
    return
```

如果没安装 `iptables`，就跳过 ACL。

```python
core.cmd(f"{ipt} -F FORWARD")
core.cmd(f"{ipt} -t nat -F")
core.cmd(f"{ipt} -P FORWARD ACCEPT")
```

这三行：

- 清空 `FORWARD` 链旧规则。
- 清空 nat 表旧规则。
- 设置默认策略为 ACCEPT。

默认允许，再针对敏感网段添加拒绝规则。

### 14.2 共享服务器区允许访问

```python
core.cmd(f"{ipt} -A FORWARD -d 10.0.100.10 -p tcp --dport 80 -j ACCEPT")
core.cmd(f"{ipt} -A FORWARD -d 10.0.100.20 -p tcp --dport 21 -j ACCEPT")
core.cmd(f"{ipt} -A FORWARD -d 10.0.100.0/24               -j ACCEPT")
```

含义：

- 允许访问 Web 服务器 `10.0.100.10` 的 TCP 80 端口。
- 允许访问 FTP 服务器 `10.0.100.20` 的 TCP 21 端口。
- 允许访问服务器区整个 `10.0.100.0/24`。

所以 A、B 两个校区的普通用户都能访问共享服务器。

### 14.3 A-HR 人事处访问控制

```python
core.cmd(f"{ipt} -A FORWARD -s 10.0.40.0/24 -d 10.0.50.0/24 -j ACCEPT")
core.cmd(f"{ipt} -A FORWARD -s 10.1.40.0/24 -d 10.0.50.0/24 -j ACCEPT")
```

允许：

- A 校区办公楼 `10.0.40.0/24` 访问 A 人事处 `10.0.50.0/24`。
- B 校区办公楼 `10.1.40.0/24` 访问 A 人事处 `10.0.50.0/24`。

后面是拒绝其他来源：

```python
core.cmd(f"{ipt} -A FORWARD -s 10.0.10.0/24 -d 10.0.50.0/24 -j DROP")
...
core.cmd(f"{ipt} -A FORWARD                 -d 10.0.50.0/24 -j DROP")
```

最后这条不写源地址，只写目的地址，表示：

> 只要目标是人事处，并且前面没有被允许，就全部拒绝。

### 14.4 A-Finance 财务处访问控制

财务处逻辑和人事处一样：

- A 办公楼允许。
- B 办公楼允许。
- 宿舍、教学楼、图书馆等拒绝。
- 其他未明确允许的来源也拒绝。

目标网段从 `10.0.50.0/24` 换成 `10.0.60.0/24`。

### 14.5 允许已建立连接的回包

```python
core.cmd(f"{ipt} -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT")
```

这条规则允许已经建立连接的返回流量。

例如办公楼访问人事处，人事处回包时也需要经过路由器。`conntrack` 能识别这是已有连接的返回包。

不过要注意，iptables 是按规则顺序匹配的。本脚本默认策略是 ACCEPT，而且前面已经对服务器、HR、Finance 做了主要控制，所以这条规则主要用于补充连接状态处理。

### 14.6 打印 ACL 规则

```python
info(core.cmd(f"{ipt} -vnL FORWARD --line-numbers"))
```

这会打印 `FORWARD` 链规则，带规则编号、命中包数量和字节数。

汇报时可以用这个命令说明 ACL 确实已经加载：

```bash
c iptables -vnL FORWARD --line-numbers
```

## 15. `start_darkstat(net)`：启动流量监控

```python
darkstat = core.cmd("command -v darkstat").strip()
if not darkstat:
    info("!!! darkstat not found; install with: sudo apt install darkstat\n")
    return False
```

先检查是否安装 `darkstat`。

`darkstat` 是轻量级流量监控工具，可以通过网页查看接口流量。

```python
log_path = "/tmp/mininet-m6-darkstat.log"
pid_path = "/tmp/mininet-m6-darkstat.pid"
```

定义日志和 pid 文件。

```python
core.cmd(
    f"{darkstat} -i any -b 0.0.0.0 -p 3001 --no-daemon "
    f"> {log_path} 2>&1 & echo $! > {pid_path}"
)
```

这条命令启动 darkstat：

- `-i any`：监听所有接口。
- `-b 0.0.0.0`：Web UI 绑定所有地址。
- `-p 3001`：Web UI 监听 3001 端口。
- `--no-daemon`：不自己后台化。

启动后可以在 Mininet 内访问：

```bash
curl http://10.0.10.254:3001
```

脚本提示的 Web UI 是：

```text
http://10.0.10.254:3001
```

## 16. `test_connectivity(net)`：自动连通性测试

这个函数验证整个网络是否按预期工作。

### 16.1 获取主机对象

```python
ad1  = net.get("ad1")
ad2  = net.get("ad2")
at1  = net.get("at1")
ao1  = net.get("ao1")
bd1  = net.get("bd1")
bo1  = net.get("bo1")
ahr1 = net.get("ahr1")
afn1 = net.get("afn1")
```

这里选出代表性主机：

- `ad1`、`ad2`：A 宿舍。
- `at1`：A 教学楼。
- `ao1`：A 办公楼。
- `bd1`：B 宿舍。
- `bo1`：B 办公楼。
- `ahr1`：A 人事处。
- `afn1`：A 财务处。

### 16.2 动态读取 DHCP IP

```python
ip_ad1  = get_host_ip(ad1)
ip_ad2  = get_host_ip(ad2)
...
```

M6 不能写死地址，所以测试前先读取每台主机当前 DHCP 分配的 IP。

### 16.3 检查 DHCP 地址是否在池内

```python
def in_pool(ip, prefix):
    if not ip.startswith(prefix):
        return False
    last = int(ip.split(".")[-1])
    return 50 <= last <= 150
```

这个辅助函数检查：

- IP 前缀是否正确，比如 `ad1` 应该是 `10.0.10.`。
- 最后一段是否在 `50` 到 `150`。

例如 `ad1 = 10.0.10.53` 是合法的，`ad1 = 10.0.20.53` 或 `10.0.10.10` 就不合法。

### 16.4 网关连通性测试

```python
r = ad1.cmd("ping -c 2 -W 2 10.0.10.254")
```

`ad1` ping 自己 VLAN 的网关 `10.0.10.254`。

如果成功，说明：

- `ad1` 的 VLAN access 端口正确。
- `s1` trunk 正常。
- `c-eth0.10` 子接口正常。
- DHCP 下发的主机地址和网关所在网段正确。

B 校区类似：

```python
bd1 ping 10.1.10.254
```

### 16.5 同 VLAN 二层互通

```python
r = ad1.cmd(f"ping -c 2 -W 2 {ip_ad2}")
```

`ad1` ping `ad2`，两者都在 A 校区宿舍 VLAN 10。

这验证同一 VLAN 内的二层通信。

### 16.6 跨 VLAN 三层路由

```python
r = ad1.cmd(f"ping -c 2 -W 2 {ip_at1}")
```

`ad1` 在 VLAN 10，`at1` 在 VLAN 20。

它们不是同一个二层广播域，通信必须经过核心路由器 `c`。

如果成功，说明单臂路由工作正常。

### 16.7 跨校区路由

```python
r = ad1.cmd(f"ping -c 2 -W 2 {ip_bd1}")
r = bd1.cmd(f"ping -c 2 -W 2 {ip_ad1}")
```

这验证 A 校区和 B 校区之间可以通过核心路由器互通。

路径大致是：

```text
ad1 -> s1 -> c-eth0.10 -> 核心路由器 c -> c-eth2.10 -> s2 -> bd1
```

反向也类似。

### 16.8 访问共享服务器

```python
r = ad1.cmd("curl -s --connect-timeout 3 http://10.0.100.10")
r = bd1.cmd("curl -s --connect-timeout 3 http://10.0.100.10")
```

这验证 A 校区和 B 校区都能访问 Web 服务器。

如果返回内容包含 `Web Server`，测试通过。

### 16.9 ACL 测试

宿舍不能访问人事处：

```python
r = ad1.cmd(f"ping -c 2 -W 2 {ip_ahr1}")
blocked = "100% packet loss" in r or "0 received" in r
```

办公楼可以访问人事处：

```python
r = ao1.cmd(f"ping -c 2 -W 2 {ip_ahr1}")
```

B 办公楼也可以访问 A 人事处：

```python
r = bo1.cmd(f"ping -c 2 -W 2 {ip_ahr1}")
```

财务处同理：

- `ad1 -> afn1` 应该被阻止。
- `bo1 -> afn1` 应该成功。

这说明 ACL 是按网段控制的，而不是按某个固定主机 IP 控制。即使 DHCP 分配的具体地址变化，只要还在对应网段，规则仍然有效。

## 17. `run()`：主启动流程

`run()` 是整个脚本的入口。

### 17.1 设置日志级别并创建拓扑

```python
setLogLevel("info")
topo = DualCampusVlanTopo()
```

设置 Mininet 日志级别，然后创建拓扑对象。

### 17.2 创建 Mininet 网络

```python
net = Mininet(
    topo=topo,
    controller=OVSController,
    switch=OVSKernelSwitch,
    autoSetMacs=True,
    autoStaticArp=False,
)
```

参数说明：

- `topo=topo`：使用前面定义的双校区拓扑。
- `controller=OVSController`：使用 OVS 控制器。
- `switch=OVSKernelSwitch`：使用 Linux 内核态 OVS 交换机。
- `autoSetMacs=True`：Mininet 自动设置 MAC，不过很多主机已经手动指定 MAC。
- `autoStaticArp=False`：不自动配置静态 ARP，因为 DHCP 动态地址场景下更适合让 ARP 正常学习。

### 17.3 启动网络

```python
net.start()
dumpNodeConnections(net.hosts)
```

`net.start()` 真正启动所有虚拟节点、交换机和链路。

`dumpNodeConnections(net.hosts)` 打印主机连接关系，方便检查拓扑是否按预期创建。

### 17.4 关键配置顺序

```python
configure_switches(net)
configure_vlan_routing(net)
start_dhcp_servers(net)
configure_vpn_addresses(net)
configure_dhcp_clients(net)
start_services(net)
configure_acl(net)
start_darkstat(net)
test_connectivity(net)
```

这个顺序很重要。

1. 先配置交换机 VLAN。否则 DHCP 报文不知道属于哪个 VLAN。
2. 再创建路由器 VLAN 子接口和网关 IP。否则 DHCP 服务没有可绑定的接口。
3. 再启动 DHCP 服务器。否则客户端发请求没人响应。
4. 配置 VPN 和外部客户端静态地址。
5. 启动 DHCP 客户端，让普通主机获取地址。
6. 启动 Web/FTP 服务。
7. 配置 ACL 访问控制。
8. 启动 darkstat 监控。
9. 执行连通性测试。

### 17.5 进入 Mininet CLI

```python
CLI(net)
```

进入交互命令行后，可以手动输入：

```bash
ad1 ip addr
ad1 ip route
ad1 ping 10.0.10.254
bd1 ip addr
bd1 curl http://10.0.100.10
c iptables -vnL FORWARD --line-numbers
```

### 17.6 清理逻辑

`finally` 块保证无论正常退出还是 Ctrl+C 中断，都会清理网络：

```python
for hname in DHCP_HOSTS:
    net.get(hname).cmd("pkill -f dhcpcd 2>/dev/null || true")
```

停止 DHCP 客户端。

```python
for subif in DHCP_RANGES:
    safe = subif.replace("-", "_").replace(".", "_")
    pf   = f"/tmp/m6-dhcp-{safe}.pid"
    core.cmd(f"[ -f {pf} ] && kill $(cat {pf}) 2>/dev/null || true; rm -f {pf}")
core.cmd("pkill -f 'keep-in-foreground' 2>/dev/null || true")
```

停止 DHCP 服务器。

```python
core.cmd("rm -f /tmp/m6-dhcp-*.leases /tmp/m6-dhcp-*.log /tmp/m6-dhcpcd-*.log")
```

删除临时日志和租约文件。

```python
for vlan_id in CAMPUS_A_VLANS:
    core.cmd(f"ip link delete c-eth0.{vlan_id} 2>/dev/null || true")
for vlan_id in CAMPUS_B_VLANS:
    core.cmd(f"ip link delete c-eth2.{vlan_id} 2>/dev/null || true")
```

删除 VLAN 子接口。

```python
net.stop()
```

停止整个 Mininet 网络。

### 17.7 文件入口

```python
if __name__ == "__main__":
    run()
```

如果直接执行这个 Python 文件，就调用 `run()`。

例如：

```bash
sudo uv run python core/topology_m6.py
```

## 18. 汇报时可以按这个顺序讲

### 18.1 第一步：总体架构

可以这样说：

> 本实验实现了一个双校区校园网。A 校区通过交换机 `s1` 接入核心路由器 `c`，B 校区通过交换机 `s2` 接入核心路由器 `c`，VPN/外部网络通过 `is` 交换机模拟。核心路由器使用 LinuxRouter，并开启 IP 转发，承担 VLAN 间路由、校区间路由、DHCP 和 ACL 功能。

### 18.2 第二步：VLAN 划分

可以这样说：

> 为了隔离不同部门，A 校区划分了宿舍、教学楼、图书馆、办公楼、人事、财务、服务器和 VPN 多个 VLAN。B 校区划分了宿舍、教学楼、图书馆和办公楼。每个 VLAN 对应一个独立网段。

### 18.3 第三步：单臂路由

可以这样说：

> 交换机到核心路由器之间是 trunk 链路，一条链路承载多个 VLAN。核心路由器在 `c-eth0` 和 `c-eth2` 上创建 802.1Q 子接口，例如 `c-eth0.10`、`c-eth0.20`、`c-eth2.10`。每个子接口配置对应 VLAN 的网关 IP，所以不同 VLAN 的主机可以通过核心路由器通信。

### 18.4 第四步：DHCP 动态分配

可以这样说：

> M6 的新增功能是 DHCP。普通终端主机初始 IP 是 `0.0.0.0`，启动后运行 `dhcpcd` 作为 DHCP 客户端。核心路由器在每个普通 VLAN 子接口上启动独立的 `dnsmasq`，为对应 VLAN 分配 `.50` 到 `.150` 的地址，并通过 DHCP Option 3 下发默认网关。

### 18.5 第五步：静态服务器和 VPN

可以这样说：

> 服务器区和 VPN 相关节点保持静态 IP，因为服务器和 VPN 节点需要稳定地址。Web 服务器是 `10.0.100.10`，FTP 服务器是 `10.0.100.20`，VPN 内网侧是 `10.0.200.10`，公网侧是 `203.0.113.1`。

### 18.6 第六步：ACL 访问控制

可以这样说：

> ACL 通过核心路由器上的 `iptables FORWARD` 链实现。共享服务器允许所有校区访问；人事和财务网段只允许 A 办公楼和 B 办公楼访问，宿舍、教学楼、图书馆等普通网段访问会被 DROP。

### 18.7 第七步：验证结果

可以这样说：

> 脚本最后会自动测试 DHCP 地址是否合法、主机到网关是否可达、同 VLAN 二层通信是否正常、跨 VLAN 和跨校区路由是否正常、服务器访问是否正常，以及 ACL 是否按预期阻止或允许访问。

## 19. 常用验证命令

运行：

```bash
sudo uv run python core/topology_m6.py
```

进入 Mininet CLI 后：

查看 DHCP 地址：

```bash
ad1 ip addr
bd1 ip addr
```

查看默认网关：

```bash
ad1 ip route
bd1 ip route
```

查看 DHCP 租约文件：

```bash
c cat /tmp/m6-dhcp-c_eth0_10.leases
c cat /tmp/m6-dhcp-c_eth2_10.leases
```

测试网关：

```bash
ad1 ping 10.0.10.254
bd1 ping 10.1.10.254
```

测试同 VLAN：

```bash
ad1 ping <ad2 的 DHCP IP>
```

测试跨 VLAN：

```bash
ad1 ping <at1 的 DHCP IP>
```

测试跨校区：

```bash
ad1 ping <bd1 的 DHCP IP>
bd1 ping <ad1 的 DHCP IP>
```

访问 Web 服务器：

```bash
ad1 curl http://10.0.100.10
bd1 curl http://10.0.100.10
```

查看 ACL：

```bash
c iptables -vnL FORWARD --line-numbers
```

查看路由器 VLAN 子接口：

```bash
c ip -d link show type vlan
c ip addr
```

查看 DHCP 服务日志：

```bash
c cat /tmp/m6-dhcp-c_eth0_10.log
ad1 cat /tmp/m6-dhcpcd-ad1.log
```

退出：

```bash
exit
```

## 20. 最容易被问到的问题

### Q1：为什么普通主机不直接写 IP？

因为 M6 要体现 DHCP 动态分配能力。普通主机创建时只给 `0.0.0.0`，启动后由 `dhcpcd` 自动向 DHCP 服务器请求 IP、网关等配置。

### Q2：为什么服务器不用 DHCP？

服务器需要稳定地址。比如 Web 服务器固定是 `10.0.100.10`，所有客户端才能稳定访问它。如果服务器地址动态变化，服务发现和测试都会变复杂。

### Q3：为什么每个 VLAN 要一个 DHCP 服务？

DHCP 请求一开始是广播，而 VLAN 之间二层隔离。VLAN 10 的广播不会自动进入 VLAN 20。把 `dnsmasq` 绑定到每个 VLAN 子接口，可以保证每个 VLAN 都有自己的 DHCP 服务和地址池。

### Q4：网关为什么一般用 `.254`？

这是一种常见规划习惯，不是强制规定。一个 `/24` 网段里可用地址通常是 `.1` 到 `.254`，很多网络会把 `.1` 或 `.254` 留给网关。本项目统一使用 `.254` 做网关，便于记忆和管理。

### Q5：A 校区和 B 校区都有 VLAN 10，会冲突吗？

不会。A 校区 VLAN 10 走 `s1` 和 `c-eth0.10`，网段是 `10.0.10.0/24`。B 校区 VLAN 10 走 `s2` 和 `c-eth2.10`，网段是 `10.1.10.0/24`。它们在不同链路和不同网段中，不会混在一起。

### Q6：主机访问不同 VLAN 时，数据包怎么走？

以 `ad1` 访问 `at1` 为例：

1. `ad1` 发现目标 IP 不在自己网段。
2. `ad1` 把包发给默认网关 `10.0.10.254`。
3. 包进入 `s1` 的 VLAN 10。
4. 通过 trunk 到达核心路由器 `c-eth0.10`。
5. 核心路由器查路由，发现目标在 VLAN 20。
6. 从 `c-eth0.20` 发出。
7. 经过 trunk 回到 `s1`，再到 `at1` 所在 access 端口。

### Q7：ACL 为什么不会因为 DHCP 地址变化失效？

因为 ACL 按网段匹配，比如 `10.0.40.0/24`、`10.0.50.0/24`，不是按某一台主机的固定 IP。只要 DHCP 分配的地址仍然在对应 VLAN 网段中，规则就有效。

### Q8：为什么代码里有 `--keep-in-foreground` 和 `-B`？

这是为了处理 Mininet network namespace。Mininet 每个节点有自己的网络命名空间。如果服务程序自己 daemonize，有可能进程不在预期的 namespace 中。代码让程序不自行后台化，再由节点 shell 使用 `&` 后台运行，可以确保进程留在正确的虚拟节点环境里。

## 21. 一句话版汇报结论

> 本实验通过 Mininet 构建了一个双校区校园网，使用 VLAN 对部门进行二层隔离，使用核心 LinuxRouter 的 802.1Q 子接口实现单臂路由和网关功能，使用 `dnsmasq` 与 `dhcpcd` 实现普通终端 DHCP 动态地址分配，同时保留服务器和 VPN 节点静态地址，并通过 `iptables` ACL 控制人事、财务等敏感网段的访问权限。
