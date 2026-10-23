# dataflow driver · 把外部 MC Agent 变成 CBAP 外设

这条驱动不碰 Minecraft，也不要求对方是 mineflayer。它只要求外部 Agent
提供一条 NDJSON 数据流：

```text
驱动 -> Agent: {"type":"cbap_hello","v":"1.0","driver":"dataflow","device_id":"..."}
Agent -> 驱动: {"type":"state","seq":1,"state":{...}}
驱动 -> Agent: {"type":"action","id":"a-1","channel":"body","op":"move","args":{...}}
Agent -> 驱动: {"type":"result","id":"a-1","ok":true,"data":{...}}
Agent -> 驱动: {"type":"event","kind":"chat","payload":{...}}
驱动 -> Agent: {"type":"estop","id":"e-1"}
```

状态 `state` 需要提供 CBAP 读取用的字段：

```json
{"pos":[100,64,100],"hp":20,"food":20,"items":{},
 "chest":{"p":[100,64,101],"items":{},"t":0},
 "scan":null,"blocks":[],"acting":"idle"}
```

设备描述和动作映射在：

```text
drivers/dataflow/device.json
drivers/dataflow/mapping.json
```

换一个 Agent 只需要改 `device_id` 和它实际支持的 ops；Kernel 不需要知道
对方是 Mineflayer、MineDojo、MCP 还是自研 Agent。

## 一个 Kernel 挂多个外设

```python
from drivers.mc.driver import McDriver
from drivers.dataflow.driver import DataFlowDriver
from kernel.legacy_runtime.server import KernelServer

legacy = McDriver("./cyberdyne.sock")
flow = DataFlowDriver("./agent.sock", device_id="mcflow://agent/my-agent")
kernel = KernelServer(drivers=[legacy, flow], socket_path="./cbap.sock")
```

测试：

```bash
python3 -m unittest -v tests.cbap.test_multi_device
```

参考假 Agent：`tests/cbap/fake_dataflow_agent.py`。
