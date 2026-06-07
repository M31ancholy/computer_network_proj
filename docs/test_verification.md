# 校园网项目 — 代码测试与验证

## 一、各里程碑核心配置代码

### M1: 基础校园网与三层路由

```bash
# 核心路由器开启IP转发
sysctl -w net.ipv4.ip_forward=1

# ACL访问控制（关键规则）
iptables -A FORWARD -s 10.0.10.0/24 -d 10.0.50.0/24 -j DROP   # 宿舍禁止访问HR
iptables -A FORWARD -s 10.0.40.0/24 -d 10.0.50.0/24 -j ACCEPT   # 办公楼允许访问HR
iptables -A FORWARD -d 10.0.50.0/24 -j DROP                      # 兜底拒绝所有访问HR
iptables -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT  # 允许回包

# Web服务器部署
mkdir -p /var/www/html
echo '<h1>Campus Web Server</h1>' > /var/www/html/index.html
python3 -m http.server 80 --directory /var/www/html &>/dev/null &

# FTP服务器部署
mkdir -p /var/ftp
echo "Welcome to Campus FTP" > /var/ftp/welcome.txt
python3 -c "
from pyftpdlib.authorizers import DummyAuthorizer;
from pyftpdlib.handlers import FTPHandler;
from pyftpdlib.servers import FTPServer;
authorizer = DummyAuthorizer();
authorizer.add_anonymous('/var/ftp');
handler = FTPHandler;
handler.authorizer = authorizer;
server = FTPServer(('0.0.0.0', 21), handler);
server.serve_forever()
" &>/dev/null &
```

### M2: VPN 外部接入

```bash
# VPN服务器生成静态密钥
openvpn --genkey --secret /tmp/mininet-vpn.key

# VPN服务器配置（关键命令）
openvpn --config /tmp/openvpn-server.conf --daemon --log /tmp/openvpn-server.log

# 外部客户端配置
openvpn --config /tmp/openvpn-client.conf --daemon --log /tmp/openvpn-client.log

# VPN服务器开启转发+NAT
sysctl -w net.ipv4.ip_forward=1
iptables -P FORWARD ACCEPT
iptables -t nat -A POSTROUTING -s 10.8.0.0/24 -d 10.0.0.0/16 -o vpn-eth1 -j MASQUERADE
iptables -A FORWARD -i tun0 -o vpn-eth1 -s 10.8.0.0/24 -d 10.0.0.0/16 -j ACCEPT
iptables -A FORWARD -i vpn-eth1 -o tun0 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
```

### M3: Darkstat 流量监控

```bash
# Darkstat启动（监听所有接口，绑定0.0.0.0:3001）
darkstat -i any -b 0.0.0.0 -p 3001 --no-daemon > /tmp/mininet-m3-darkstat.log 2>&1 &
echo $! > /tmp/mininet-m3-darkstat.pid
```

### M4: VLAN 与单臂路由

```bash
# 加载802.1Q模块
modprobe 8021q

# 路由器创建VLAN子接口
ip link add link c-eth0 name c-eth0.10 type vlan id 10
ip addr add 10.0.10.254/24 dev c-eth0.10
ip link set c-eth0.10 up

ip link add link c-eth0 name c-eth0.20 type vlan id 20
ip addr add 10.0.20.254/24 dev c-eth0.20
ip link set c-eth0.20 up

ip link add link c-eth0 name c-eth0.30 type vlan id 30
ip addr add 10.0.30.254/24 dev c-eth0.30
ip link set c-eth0.30 up

ip link add link c-eth0 name c-eth0.40 type vlan id 40
ip addr add 10.0.40.254/24 dev c-eth0.40
ip link set c-eth0.40 up

ip link add link c-eth0 name c-eth0.50 type vlan id 50
ip addr add 10.0.50.254/24 dev c-eth0.50
ip link set c-eth0.50 up

ip link add link c-eth0 name c-eth0.60 type vlan id 60
ip addr add 10.0.60.254/24 dev c-eth0.60
ip link set c-eth0.60 up

ip link add link c-eth0 name c-eth0.100 type vlan id 100
ip addr add 10.0.100.254/24 dev c-eth0.100
ip link set c-eth0.100 up

ip link add link c-eth0 name c-eth0.200 type vlan id 200
ip addr add 10.0.200.254/24 dev c-eth0.200
ip link set c-eth0.200 up

# OVS交换机设置fail-mode和默认流表
ovs-vsctl set-fail-mode s1 standalone
ovs-ofctl add-flow s1 priority=0,actions=NORMAL

# OVS交换机access端口打VLAN tag
ovs-vsctl set port s1-eth2 tag=10    # A-Dorm VLAN 10
ovs-vsctl set port s1-eth4 tag=20    # A-Teaching VLAN 20
ovs-vsctl set port s1-eth5 tag=30    # A-Library VLAN 30
ovs-vsctl set port s1-eth6 tag=40    # A-Office VLAN 40
ovs-vsctl set port s1-eth7 tag=50    # A-HR VLAN 50
ovs-vsctl set port s1-eth8 tag=60    # A-Finance VLAN 60
ovs-vsctl set port s1-eth9 tag=100   # Server VLAN 100
ovs-vsctl set port s1-eth10 tag=200  # VPN-In VLAN 200
```

### M5: 双校区网络扩展

```bash
# B校区VLAN子接口配置
ip addr flush dev c-eth2
ip link set c-eth2 up

ip link add link c-eth2 name c-eth2.10 type vlan id 10
ip addr add 10.1.10.254/24 dev c-eth2.10
ip link set c-eth2.10 up

ip link add link c-eth2 name c-eth2.20 type vlan id 20
ip addr add 10.1.20.254/24 dev c-eth2.20
ip link set c-eth2.20 up

ip link add link c-eth2 name c-eth2.30 type vlan id 30
ip addr add 10.1.30.254/24 dev c-eth2.30
ip link set c-eth2.30 up

ip link add link c-eth2 name c-eth2.40 type vlan id 40
ip addr add 10.1.40.254/24 dev c-eth2.40
ip link set c-eth2.40 up

# 跨校区ACL（B办公楼访问A人事/财务）
iptables -A FORWARD -s 10.1.40.0/24 -d 10.0.50.0/24 -j ACCEPT
iptables -A FORWARD -s 10.1.40.0/24 -d 10.0.60.0/24 -j ACCEPT

# B校区交换机配置
ovs-vsctl set-fail-mode s2 standalone
ovs-ofctl add-flow s2 priority=0,actions=NORMAL

# B校区access端口打VLAN tag
ovs-vsctl set port s2-eth2 tag=10    # B-Dorm VLAN 10
ovs-vsctl set port s2-eth3 tag=20    # B-Teaching VLAN 20
ovs-vsctl set port s2-eth4 tag=30    # B-Library VLAN 30
ovs-vsctl set port s2-eth5 tag=40    # B-Office VLAN 40
```

### M6: DHCP 动态地址分配

```bash
# 核心路由器启动多实例dnsmasq（每个VLAN子接口一个）
dnsmasq --keep-in-foreground --no-ping --interface=c-eth0.10 \
  --bind-interfaces --port=0 --dhcp-range=10.0.10.50,10.0.10.150,12h \
  --dhcp-option=3,10.0.10.254 --dhcp-leasefile=/tmp/m6-dhcp-c_eth0_10.leases \
  --pid-file=/tmp/m6-dhcp-c_eth0_10.pid --log-facility=- \
  > /tmp/m6-dhcp-c_eth0_10.log 2>&1 &

dnsmasq --keep-in-foreground --no-ping --interface=c-eth0.20 \
  --bind-interfaces --port=0 --dhcp-range=10.0.20.50,10.0.20.150,12h \
  --dhcp-option=3,10.0.20.254 --dhcp-leasefile=/tmp/m6-dhcp-c_eth0_20.leases \
  --pid-file=/tmp/m6-dhcp-c_eth0_20.pid --log-facility=- \
  > /tmp/m6-dhcp-c_eth0_20.log 2>&1 &

dnsmasq --keep-in-foreground --no-ping --interface=c-eth0.30 \
  --bind-interfaces --port=0 --dhcp-range=10.0.30.50,10.0.30.150,12h \
  --dhcp-option=3,10.0.30.254 --dhcp-leasefile=/tmp/m6-dhcp-c_eth0_30.leases \
  --pid-file=/tmp/m6-dhcp-c_eth0_30.pid --log-facility=- \
  > /tmp/m6-dhcp-c_eth0_30.log 2>&1 &

dnsmasq --keep-in-foreground --no-ping --interface=c-eth0.40 \
  --bind-interfaces --port=0 --dhcp-range=10.0.40.50,10.0.40.150,12h \
  --dhcp-option=3,10.0.40.254 --dhcp-leasefile=/tmp/m6-dhcp-c_eth0_40.leases \
  --pid-file=/tmp/m6-dhcp-c_eth0_40.pid --log-facility=- \
  > /tmp/m6-dhcp-c_eth0_40.log 2>&1 &

dnsmasq --keep-in-foreground --no-ping --interface=c-eth0.50 \
  --bind-interfaces --port=0 --dhcp-range=10.0.50.50,10.0.50.150,12h \
  --dhcp-option=3,10.0.50.254 --dhcp-leasefile=/tmp/m6-dhcp-c_eth0_50.leases \
  --pid-file=/tmp/m6-dhcp-c_eth0_50.pid --log-facility=- \
  > /tmp/m6-dhcp-c_eth0_50.log 2>&1 &

dnsmasq --keep-in-foreground --no-ping --interface=c-eth0.60 \
  --bind-interfaces --port=0 --dhcp-range=10.0.60.50,10.0.60.150,12h \
  --dhcp-option=3,10.0.60.254 --dhcp-leasefile=/tmp/m6-dhcp-c_eth0_60.leases \
  --pid-file=/tmp/m6-dhcp-c_eth0_60.pid --log-facility=- \
  > /tmp/m6-dhcp-c_eth0_60.log 2>&1 &

dnsmasq --keep-in-foreground --no-ping --interface=c-eth2.10 \
  --bind-interfaces --port=0 --dhcp-range=10.1.10.50,10.1.10.150,12h \
  --dhcp-option=3,10.1.10.254 --dhcp-leasefile=/tmp/m6-dhcp-c_eth2_10.leases \
  --pid-file=/tmp/m6-dhcp-c_eth2_10.pid --log-facility=- \
  > /tmp/m6-dhcp-c_eth2_10.log 2>&1 &

dnsmasq --keep-in-foreground --no-ping --interface=c-eth2.20 \
  --bind-interfaces --port=0 --dhcp-range=10.1.20.50,10.1.20.150,12h \
  --dhcp-option=3,10.1.20.254 --dhcp-leasefile=/tmp/m6-dhcp-c_eth2_20.leases \
  --pid-file=/tmp/m6-dhcp-c_eth2_20.pid --log-facility=- \
  > /tmp/m6-dhcp-c_eth2_20.log 2>&1 &

dnsmasq --keep-in-foreground --no-ping --interface=c-eth2.30 \
  --bind-interfaces --port=0 --dhcp-range=10.1.30.50,10.1.30.150,12h \
  --dhcp-option=3,10.1.30.254 --dhcp-leasefile=/tmp/m6-dhcp-c_eth2_30.leases \
  --pid-file=/tmp/m6-dhcp-c_eth2_30.pid --log-facility=- \
  > /tmp/m6-dhcp-c_eth2_30.log 2>&1 &

dnsmasq --keep-in-foreground --no-ping --interface=c-eth2.40 \
  --bind-interfaces --port=0 --dhcp-range=10.1.40.50,10.1.40.150,12h \
  --dhcp-option=3,10.1.40.254 --dhcp-leasefile=/tmp/m6-dhcp-c_eth2_40.leases \
  --pid-file=/tmp/m6-dhcp-c_eth2_40.pid --log-facility=- \
  > /tmp/m6-dhcp-c_eth2_40.log 2>&1 &

# 客户端启动dhcpcd获取IP（每台主机上执行）
ip addr flush dev ad1-eth0
ip link set ad1-eth0 up
dhcpcd -B -t 15 ad1-eth0 > /tmp/m6-dhcpcd-ad1.log 2>&1 &

# 查看DHCP租约
ls /tmp/*.leases

# 查看dnsmasq进程数
pgrep -c -f 'keep-in-foreground'
```

## 二、自动连通性测试代码（test_connectivity）

以下代码来自 `core/topology_m6.py` 中的 `test_connectivity()` 函数，脚本启动后自动执行。

```bash
# 1. DHCP地址合法性验证：检查IP是否在.50-.150动态池内
ad1 ip -4 addr show dev ad1-eth0

# 2. 网关连通性（VLAN tag + 子接口基础验证）
ad1 ping -c 2 -W 2 10.0.10.254
bd1 ping -c 2 -W 2 10.1.10.254

# 3. 同校区同VLAN二层互通
ad1 ping -c 2 -W 2 <ad2_ip>

# 4. 同校区跨VLAN三层路由
ad1 ping -c 2 -W 2 <at1_ip>

# 5. 跨校区路由（A <-> B）
ad1 ping -c 2 -W 2 <bd1_ip>
bd1 ping -c 2 -W 2 <ad1_ip>

# 6. 共享服务器（两校区都能访问）
ad1 curl -s --connect-timeout 3 http://10.0.100.10
bd1 curl -s --connect-timeout 3 http://10.0.100.10

# 7. ACL：A宿舍不能访问A-HR
ad1 ping -c 2 -W 2 <ahr1_ip>

# 8. ACL：A办公楼可以访问A-HR
ao1 ping -c 2 -W 2 <ahr1_ip>

# 9. ACL：B办公楼可以访问A-HR（跨校区协作）
bo1 ping -c 2 -W 2 <ahr1_ip>

# 10. ACL：A宿舍不能访问A-Finance
ad1 ping -c 2 -W 2 <afn1_ip>

# 11. ACL：B办公楼可以访问A-Finance
bo1 ping -c 2 -W 2 <afn1_ip>

# 查看ACL规则列表
iptables -vnL FORWARD --line-numbers
```

> 注意：`<xxx_ip>` 表示需要先通过 `ip -4 addr show dev xxx-eth0` 动态获取该主机的DHCP分配地址后再填入。

## 三、Mininet CLI 手动验证命令与结果

以下为报告"结果分析"章节中记录的全部 11 项验证测试，在 Mininet CLI 中手动执行。

### 1. DHCP 功能验证

验证终端能否自动获取正确的 IP 地址、子网掩码和默认网关。

```bash
mininet> ad1 ip addr
```

**预期结果：** ad1 的 eth0 接口应显示 DHCP 分配的 IP 地址（如 10.0.10.50~10.0.10.150），无需人工配置。

---

### 2. DHCP 网关验证

验证 DHCP 服务是否正确下发 Option 3 默认网关参数。

```bash
mininet> bd1 ip route
mininet> ad1 ip route
```

**预期结果：** bd1 默认路由为 `via 10.1.10.254`，ad1 默认路由为 `via 10.0.10.254`，不同 VLAN、不同校区终端获取到所属网段的标准网关地址。

---

### 3. VLAN 内部通信

验证同一 VLAN 内主机能否正常二层通信。

```bash
mininet> ad1 ping ad2
```

**预期结果：** ping 成功（0% packet loss），说明 OVS VLAN 划分和二层转发正常。

---

### 4. 跨 VLAN 路由测试

#### 4a. A 校区宿舍 → A 校区教学楼

```bash
mininet> ad1 ping at1
```

**预期结果：** ping 成功，核心路由器 802.1Q 子接口和三层转发配置正确。

#### 4b. A 校区宿舍 → A 校区财务处（ACL 验证）

```bash
mininet> ad1 ping afn1
```

**预期结果：** ping 被拒绝（100% packet loss），宿舍区等普通用户无法访问财务处等敏感网段；办公楼可以正常访问，说明 ACL 规则生效。

---

### 5. 跨校区通信测试

验证 A、B 两个校区之间能否正常通信。

```bash
mininet> at1 ping bt1
```

**预期结果：** ping 成功，双校区路由配置正确，网络互联方案可行。

---

### 6. Web 服务器测试

验证各网段终端能否访问共享 Web 服务器。

```bash
mininet> ad1 curl http://10.0.100.10
```

**预期结果：** 返回包含 "Campus Web Server" 的 HTML 页面内容，说明 Web 服务部署正常、路由可达。

---

### 7. DHCP 租约验证

验证多实例 dnsmasq 相互独立运行，不同 VLAN 的地址租约分开存储。

```bash
mininet> c ls /tmp/*.leases
```

**预期结果：** 列出多个独立的 lease 文件（如 m6-dhcp-c_eth0_10.leases、m6-dhcp-c_eth2_10.leases 等），各 VLAN 租约互不干扰。

---

### 8. 路由路径验证

查看跨校区数据包的完整路由路径。

```bash
mininet> ad1 traceroute 10.1.10.52
```

**预期结果：** 第一跳为本地网关 10.0.10.254，第二跳直达目标主机 10.1.10.52，路由路径清晰。

---

### 9. FTP 测试

验证终端能否连接 FTP 服务器。

```bash
mininet> ad1 ftp 10.0.100.20
```

**预期结果：** 成功连接 FTP 服务器，可看到欢迎信息和文件列表，内网 FTP 文件共享服务运行正常。

---

### 10. VPN 测试

验证外部客户端通过 VPN 隧道能否访问校园内网资源。

```bash
mininet> ex curl 10.0.100.10
```

**预期结果：** 返回包含 "Campus Web Server" 的页面内容，验证 OpenVPN 隧道、NAT 转发、IP 转发规则全部生效；同时原有 ACL 安全策略未被破坏。

---

### 11. Darkstat 流量监测

验证流量监控 Web UI 是否正常工作。

```bash
mininet> c curl http://10.0.10.254:3001
mininet> bd1 curl http://10.1.10.254:3001
```

**预期结果：** Darkstat 网页端正常展示全网所有在线主机 IP、上下行流量、总流量、在线状态等数据，可实时统计核心链路、各网段、VPN 流量。