# 校园网构建项目

基于 Mininet 的校园网络模拟项目，实现二层互通、三层路由和访问控制。

## 项目结构

```
campus_network/
├── topology.py          # 完整版校园网拓扑
├── simple_topo.py       # 简化版拓扑（用于快速测试）
├── configs/             # 配置文件目录
├── scripts/             # 辅助脚本
└── docs/               # 文档
```

## 网络拓扑

### 完整版拓扑

```
核心层：Core Switch (三层交换机/路由器)
    ├── 学生宿舍区 (VLAN 10, 10.0.10.0/24)
    ├── 教学楼区   (VLAN 20, 10.0.20.0/24)
    ├── 图书馆区   (VLAN 30, 10.0.30.0/24)
    ├── 办公楼区   (VLAN 40, 10.0.40.0/24)
    ├── 人事处     (VLAN 50, 10.0.50.0/24) [受限访问]
    ├── 财务处     (VLAN 60, 10.0.60.0/24) [受限访问]
    └── 服务器区   (VLAN 100, 10.0.100.0/24)
```

### 简化版拓扑

```
核心交换机
├── 学生宿舍 (h1, h2)
├── 教学楼   (h3)
├── 人事处   (h4) [受限]
└── Web服务器
```

## 环境要求

- Python 3.8+
- Mininet 2.3+
- Open vSwitch
- Linux 操作系统（Ubuntu/Debian 推荐）

## 安装依赖

```bash
# 安装 Mininet（Ubuntu）
sudo apt-get update
sudo apt-get install mininet

# 安装 Python 依赖
uv sync
```

## 运行项目

### 运行简化版（推荐首次运行）

```bash
sudo uv run python campus_network/simple_topo.py
```

### 运行完整版

```bash
sudo uv run python campus_network/topology.py
```

## Mininet CLI 常用命令

进入 CLI 后可使用以下命令：

```bash
# 查看所有节点
mininet> nodes

# 查看所有链路
mininet> links

# 测试连通性
mininet> h1 ping h2          # 学生宿舍内部
mininet> h1 ping h3          # 学生宿舍 -> 教学楼
mininet> h1 ping h4          # 学生宿舍 -> 人事处（应该失败）

# 访问 Web 服务器
mininet> h1 curl 10.0.100.10

# 查看主机网络配置
mininet> h1 ifconfig

# 查看路由表
mininet> h1 route -n

# 退出
mininet> exit
```

## 功能验证

### 1. 二层互通（同一部门）

```bash
mininet> dorm_h1 ping dorm_h2
# 应该成功 - 同一 VLAN 内
```

### 2. 三层互通（跨部门）

```bash
mininet> dorm_h1 ping teaching_h1
# 应该成功 - 通过核心路由器
```

### 3. 访问 Web/FTP 服务器

```bash
mininet> dorm_h1 curl 10.0.100.10
# 应该返回 Web 页面内容
```

### 4. 访问控制验证

```bash
mininet> dorm_h1 ping hr_h1
# 应该失败 - 学生宿舍无法访问人事处

mininet> office_h1 ping hr_h1
# 应该成功 - 办公楼可以访问人事处
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
mininet> h1 ifconfig

# 检查路由表
mininet> h1 route -n

# 检查 ARP 表
mininet> h1 arp -a

# 检查交换机状态
mininet> s1 ovs-vsctl show
```

### 问题 2: 访问控制不生效

```bash
# 检查 iptables 规则
mininet> core iptables -L -n -v

# 手动添加规则
mininet> core iptables -A FORWARD -s 10.0.1.0/24 -d 10.0.3.0/24 -j DROP
```

### 问题 3: Web 服务无法访问

```bash
# 检查服务是否运行
mininet> web ps aux | grep python

# 手动启动服务
mininet> web python3 -m http.server 80
```

## 扩展功能

### 添加新部门

编辑 `topology.py`：

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
self.addLink(new_sw, core_switch)
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

1. **需要 root 权限**: 运行脚本需要 sudo
2. **网络隔离**: Mininet 创建的网络是隔离的，不影响宿主机网络
3. **端口冲突**: 确保 80、21 等端口未被占用
4. **资源限制**: 完整版拓扑会创建较多虚拟设备，注意系统资源

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