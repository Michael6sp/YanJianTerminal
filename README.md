# 岩鉴 Terminal V0.2

Air Operations Console / 空端综合操作台。独立电脑端 WebSocket Server，用于接收 AirBridge 状态、遥测、Candidate、照片元数据及 H.264/H.265 视频，并向 AirBridge 发送控制命令。

## 安装与启动

```bash
cd /Users/lsp/Desktop/YanJianTerminal
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

Terminal 默认监听 `0.0.0.0:8765`。数据库自动创建于 `data/yanjian_terminal.db`。

## 无飞机模拟

先启动 Terminal，再在另一个终端运行：

```bash
cd /Users/lsp/Desktop/YanJianTerminal
source .venv/bin/activate
python mock_airbridge.py
```

Mock 会发送 hello、status、telemetry、heartbeat、candidate 和 photo_meta，并响应全部 command。V0.2 mock 不模拟视频。

## 测试

```bash
python -m compileall -q .
python -m unittest -v tests.test_core
```

## 结构

- `websocket_server.py`：后台 asyncio WebSocket Server
- `video_decoder.py`：独立 QThread + PyAV 流式解码
- `data/database.py`：SQLite 表结构与持久化
- `managers/`：Candidate、Alarm、Command 管理
- `models/`：Candidate 与 Telemetry 模型
- `ui/main_window.py`：V0.2 综合操作台
- `mock_airbridge.py`：无飞机协议模拟器
