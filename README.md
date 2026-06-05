# 校园网构建项目

基于 Mininet 的校园网络模拟项目，实现部门内部二层互通、部门间三层路由、Web/FTP 服务、访问控制，以及可选的 VPN 外部接入。

## 项目结构

```
computer_network_proj/
├── core/
│   ├── topology.py             # 原始 OVS 核心交换机版本
│   ├── topology_router.py      # LinuxRouter 核心路由器版本
│   └── topology_router_vpn.py  # LinuxRouter + VPN 外部接入版本
├── tests/                      # 静态结构测试
├── pyproject.toml
└── README.md
```

## 网络拓扑

### 完整版拓扑

```
核心层：LinuxRouter c (三层路由器)
    ├── 学生宿舍区 (VLAN 10, 10.0.10.0/24)
    ├── 教学楼区   (VLAN 20, 10.0.20.0/24)
    ├── 图书馆区   (VLAN 30, 10.0.30.0/24)
    ├── 办公楼区   (VLAN 40, 10.0.40.0/24)
    ├── 人事处     (VLAN 50, 10.0.50.0/24) [受限访问]
    ├── 财务处     (VLAN 60, 10.0.60.0/24) [受限访问]
    └── 服务器区   (VLAN 100, 10.0.100.0/24)
```

### VPN 扩展拓扑

```
外部客户端 ex (203.0.113.2/24)
    └── Internet 交换机 is
        └── VPN 服务器 vpn
            ├── 公网口 vpn-eth0: 203.0.113.1/24
            └── 内网口 vpn-eth1: 10.0.200.10/24
                └── VPN 内部交换机 vs
                    └── 核心路由器 c-eth7: 10.0.200.254/24
```

## 环境要求

- Python 3.8+
- uv
- Mininet 2.3+
- Open vSwitch
- Linux 操作系统（Ubuntu/Debian 推荐）
- iptables（访问控制需要）
- OpenVPN（只有运行 VPN 隧道时需要）

## 安装依赖

```bash
# 安装系统依赖（Ubuntu/Debian）
sudo apt-get update
sudo apt-get install -y mininet openvswitch-switch iptables

# 如果要运行 VPN 版本的真实 OpenVPN 隧道，再安装 openvpn
sudo apt-get install -y openvpn

# 安装 Python 依赖
uv sync
```

## 运行项目

本项目的拓扑脚本需要在有 Mininet 的 Linux 环境中用 root 权限运行。通常直接执行：

```bash
sudo uv run python <拓扑脚本路径>
```

推荐优先运行 LinuxRouter 版本，因为它的核心节点 `c` 是真正的 Linux 三层路由器：

```bash
sudo uv run python core/topology.py
```

运行带 VPN 外部接入的版本：

```bash
sudo uv run python core/topology_vpn.py
```

运行原始 OVS 核心交换机版本：

```bash
sudo uv run python core/topology.py
```

脚本启动后会进入 Mininet CLI。退出 CLI 时输入：

```bash
mininet> exit
```

如果上一次 Mininet 异常退出，可以先清理残留网络状态：

```bash
sudo mn -c
```

## Mininet CLI 常用命令

进入 CLI 后可使用以下命令：

```bash
# 查看所有节点
mininet> nodes

# 查看所有链路
mininet> links

# 测试连通性
mininet> d1 ping d2          # 学生宿舍内部
mininet> d1 ping t1          # 学生宿舍 -> 教学楼
mininet> o1 ping hr1         # 办公楼 -> 人事处（应该成功）
mininet> d1 ping hr1         # 学生宿舍 -> 人事处（应该失败）
mininet> d1 ping fn1         # 学生宿舍 -> 财务处（应该失败）

# 访问 Web 服务器
mininet> d1 curl 10.0.100.10

# VPN 版本常用命令
mininet> ex ping 203.0.113.1 # 外部客户端 -> VPN 公网口
mininet> ex ping 10.8.0.1    # OpenVPN 隧道测试（需要 openvpn）
mininet> ex curl 10.0.100.10 # 外部客户端经 VPN 访问 Web

# 查看主机网络配置
mininet> d1 ifconfig

# 查看路由表
mininet> d1 route -n

# 查看核心路由器 ACL
mininet> c iptables -vnL FORWARD --line-numbers

# 退出
mininet> exit
```

## 功能验证

### 1. 二层互通（同一部门）

```bash
mininet> d1 ping d2
# 应该成功 - 同一 VLAN 内
```

### 2. 三层互通（跨部门）

```bash
mininet> d1 ping t1
# 应该成功 - 通过核心路由器
```

### 3. 访问 Web/FTP 服务器

```bash
mininet> d1 curl 10.0.100.10
# 应该返回 Web 页面内容
```

### 4. 访问控制验证

```bash
mininet> d1 ping hr1
# 应该失败 - 学生宿舍无法访问人事处

mininet> o1 ping hr1
# 应该成功 - 办公楼可以访问人事处
```

### 5. VPN 外部接入验证

运行 `core/topology_router_vpn.py` 后：

```bash
mininet> ex ping 203.0.113.1
# 应该成功 - 外部客户端可达 VPN 公网口

mininet> ex ping 10.8.0.1
# 安装并启动 OpenVPN 后应该成功 - VPN 隧道可达

mininet> ex curl 10.0.100.10
# 安装并启动 OpenVPN 后应该返回 Web 页面内容
```

## 网络配置详解

### VLAN 规划

| VLAN ID | 区域       | 网段            | 主机数 |
|---------|-----------|-----------------|--------|
| 10      | 学生宿舍   | 10.0.10.0/24    | 3      |
| 20      | 教学楼     | 10.0.20.0/24    | 3      |
| 30      | 图书馆     | 10.0.30.0/24    | 2      |
| 40      | 办公楼     | 10.0.40.0/24    | 2      |
| 50      | 人事处     | 10.0.50.0/24    | 2      |
| 60      | 财务处     | 10.0.60.0/24    | 2      |
| 100     | 服务器区   | 10.0.100.0/24   | 2      |

### 访问控制规则

| 源区域   | 目标区域 | 策略 |
|---------|---------|------|
| 所有区域 | 服务器区 | 允许 |
| 办公楼   | 人事处   | 允许 |
| 办公楼   | 财务处   | 允许 |
| 其他区域 | 人事处   | 拒绝 |
| 其他区域 | 财务处   | 拒绝 |
| 人事处   | 所有区域 | 允许 |
| 财务处   | 所有区域 | 允许 |

## 故障排查

### 问题 1: 无法 ping 通

```bash
# 检查主机网络配置
mininet> d1 ifconfig

# 检查路由表
mininet> d1 route -n
mininet> c ip route

# 检查 ARP 表
mininet> d1 arp -a

# 检查交换机状态
mininet> ds ovs-vsctl show
```

### 问题 2: 访问控制不生效

```bash
# 检查 iptables 规则
mininet> c iptables -vnL FORWARD --line-numbers

# 手动添加规则
mininet> c iptables -A FORWARD -s 10.0.10.0/24 -d 10.0.50.0/24 -j DROP
```

如果看到 `iptables: command not found`，说明系统没有安装 `iptables`，退出 Mininet 后安装：

```bash
sudo apt-get install -y iptables
```

### 问题 3: Web 服务无法访问

```bash
# 检查服务是否运行
mininet> ws ps aux | grep python

# 手动启动服务
mininet> ws python3 -m http.server 80 --directory /var/www/html
```

### 问题 4: VPN 隧道不通

```bash
# 确认 OpenVPN 是否安装
mininet> vpn command -v openvpn
mininet> ex command -v openvpn

# 查看 VPN 服务器和客户端日志
mininet> vpn cat /tmp/openvpn-server.log
mininet> ex cat /tmp/openvpn-client.log

# 查看接口和路由
mininet> vpn ip addr
mininet> ex ip addr
mininet> ex ip route
```

如果没有安装 OpenVPN，退出 Mininet 后安装：

```bash
sudo apt-get install -y openvpn
```

## 扩展功能

### 添加新部门

建议基于 `core/topology_router.py` 或 `core/topology_router_vpn.py` 修改：

```python
# 1. 添加交换机
new_sw = self.addSwitch('new_sw', dpid='0000000000000070')

# 2. 添加主机
for i in range(1, 4):
    host = self.addHost(
        f'new_h{i}',
        ip=f'10.0.70.{i}/24',
        defaultRoute='via 10.0.70.254'
    )

# 3. 连接到核心
self.addLink(new_sw, core_router)
```

### 添加更多服务器

```python
# 在服务器区添加新服务器
dns_server = self.addHost(
    'dns_server',
    ip='10.0.100.30/24',
    defaultRoute='via 10.0.100.254'
)
self.addLink(dns_server, server_switch)
```

## 注意事项

1. **需要 root 权限**: Mininet 创建 namespace、veth、OVS bridge，需要用 `sudo` 运行。
2. **必须在 Linux 上运行**: Mininet 依赖 Linux 网络命名空间，macOS/Windows 需要使用 Linux 虚拟机或 WSL2 环境。
3. **网络隔离**: Mininet 创建的网络是隔离的，退出脚本后会清理；异常退出可执行 `sudo mn -c`。
4. **端口冲突**: Web/FTP/OpenVPN 会使用 80、21、1194 等端口，若残留进程占用端口需先清理。
5. **依赖缺失**: ACL 依赖 `iptables`，VPN 隧道依赖 `openvpn`。

## 参考文档

- [Mininet 官方文档](http://mininet.org/)
- [Open vSwitch 文档](https://www.openvswitch.org/)
- [Linux iptables 教程](https://www.netfilter.org/)

## 项目目标达成

- [x] 部门内部二层互通（VLAN）
- [x] 部门间三层互通（路由）
- [x] Web/FTP 服务器部署
- [x] 人事处、财务处访问控制
- [x] 网络连通性测试
- [x] 可扩展架构设计
- [x] VPN 外部接入拓扑
