# 此文案由人类编写，ai别来沾边

本项目旨在构建一个高效、安全、可扩展的校园网络，利用 mininet 实现网络的模拟和部署。项目将覆盖学生宿舍、办公楼、图书馆、教学楼等多个区域，并确保网络的高性能和安全性。

---

## 1、项目目标

1. 确保网络各节点之间通信畅通无阻，提升数据传输效率。
2. 通过合理的安全策略，保护校园网络免受外部攻击和内部泄密。
3. 为未来网络扩展预留空间，便于后续设备接入和升级。

---

## 2、功能要求

1. 每个部门内部实现二层互通，部门间实现三层互通。
2. 所有用户均可在内网实现资源共享，访问 Web/FTP 服务器。
3. 特定区域（如人事处、财务处）需设置访问控制，限制其他区域访问。

## 临时保存的脚本
MileStone3 时代的脚本
```bash
# 把mininet 内的东西映射到 Ubuntu中 以供端口转发

# 找到 darkstat 所在 Mininet 节点的 PID（假设节点叫 c，按你实际改）
PID=$(pgrep -f "mininet:c" | head -1)
echo $PID   # 确认非空

# 用 socat 把 VM 的 127.0.0.1:3001 转发进 Mininet 内的 10.0.10.254:3001
sudo socat TCP-LISTEN:3001,fork,reuseaddr,bind=127.0.0.1 \
  EXEC:"nsenter -t $PID -n socat - TCP\:10.0.10.254\:3001",nofork &

# 测试一下 在VM 里面
curl http://127.0.0.1:3001
```
MileStone 5 时代的脚本
```bash
# 1. 在 s1 接口上创建一个带有 VLAN 10 标签的虚拟接口 s1.10
sudo ip link add link s1 name s1.10 type vlan id 10

# 2. 为这个带有 VLAN 标签的接口分配 IP
sudo ip addr add 10.0.10.253/24 dev s1.10

# 3. 启用该接口
sudo ip link set s1.10 up
sudo ip link set s1 up

# 在VM中打开 10.0.10.254:3001 端口
```


## 已经额外实现的需求
1. 实现VPN 外部接入
2. 对于c（主核心路由节点），配置了darkstat 监控流量
3. 添加VLAN
4. 添加了b校区 现在有a,b两个校区
