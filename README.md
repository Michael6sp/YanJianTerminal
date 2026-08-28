# 岩鉴 Terminal V0.1

独立电脑端 WebSocket Server，用于接收 AirBridge 状态、遥测和 H.264/H.265 视频，并向 AirBridge 发送控制命令。

## 启动

```bash
cd /Users/lsp/Desktop/YanJianTerminal
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

Terminal 默认监听 `0.0.0.0:8765`。

## 结构

- `main.py`：程序入口
- `websocket_server.py`：后台 asyncio WebSocket Server
- `video_decoder.py`：独立 QThread + PyAV 流式解码
- `protocol.py`：JSON 消息和 command 生成
- `state.py`：界面状态
- `ui/main_window.py`：主界面及 Qt 信号连接
