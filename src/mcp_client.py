"""
mcp_client.py - 实验性 MCP 客户端 (默认关闭)

MCP (Model Context Protocol) 让 agent 连接外部工具服务器，
动态获取和调用服务器提供的工具。

此模块默认不加载，不影响其他功能。所有 MCP 相关 import 都在函数内部懒加载。

开启方式:
  启动时: python -m src.main --mcp mcp_config.json
  运行时: /mcp enable mcp_config.json

需要额外安装: pip install mcp httpx

配置文件格式 (兼容 mcp-api-server/mcp.json.example):
    {
      "mcpServers": {
        "server-name": {
          "command": "python",
          "args": ["path/to/server.py"],
          "env": {"API_KEY": "..."}
        }
      }
    }
"""

import asyncio
import json
import os
import threading
from pathlib import Path


class McpBridge:
    """MCP 客户端桥接器。

    负责:
    - 启动 MCP 服务器子进程并建立 stdio 连接
    - 将 MCP 工具转换为 Anthropic 格式并注入 agent
    - 在同步的 agent_loop 中调用异步的 MCP 接口
    """

    def __init__(self):
        self._contexts = {}
        self.tools = []
        self.handlers = {}
        self.connected = False
        self._loop = None
        self._thread = None

    def _ensure_loop(self):
        """启动一个后台事件循环，用于桥接 sync/async。"""
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
            self._thread.start()

    def _run_async(self, coro):
        """在后台事件循环中运行异步协程并等待结果。"""
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=30)

    def connect(self, config_path: str) -> str:
        """读取配置文件，连接所有 MCP 服务器。"""
        try:
            from mcp import ClientSession, StdioServerParameters  # noqa: F401
            from mcp.client.stdio import stdio_client  # noqa: F401
        except ImportError:
            return ("Error: mcp library not installed.\n"
                    "Install with: pip install mcp httpx")

        config = json.loads(Path(config_path).read_text())
        servers = config.get("mcpServers", {})
        if not servers:
            return "Error: no mcpServers found in config"

        results = []
        for name, cfg in servers.items():
            try:
                self._run_async(self._connect_one(name, cfg))
                count = sum(1 for t in self.tools if t["name"].startswith(f"mcp_{name}_"))
                results.append(f"  {name}: {count} tools")
            except Exception as e:
                results.append(f"  {name}: failed ({e})")

        self.connected = bool(self._contexts)
        header = f"MCP: {len(self.tools)} tools from {len(self._contexts)} servers"
        return "\n".join([header] + results)

    async def _connect_one(self, name, cfg):
        """连接一个 MCP 服务器并注册其工具。"""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=cfg["command"],
            args=cfg.get("args", []),
            env={**os.environ, **cfg.get("env", {})}
        )
        ctx = stdio_client(params)
        read, write = await ctx.__aenter__()
        session = ClientSession(read, write)
        await session.__aenter__()
        await session.initialize()
        self._contexts[name] = (ctx, session)

        tools_result = await session.list_tools()
        for tool in tools_result.tools:
            full_name = f"mcp_{name}_{tool.name}"
            self.tools.append({
                "name": full_name,
                "description": f"[MCP:{name}] {tool.description or tool.name}",
                "input_schema": tool.inputSchema,
            })
            sn, tn = name, tool.name

            def make_handler(server_name, tool_name):
                def handler(**kwargs):
                    return self._call_tool(server_name, tool_name, kwargs)
                return handler
            self.handlers[full_name] = make_handler(sn, tn)

    def _call_tool(self, server_name, tool_name, arguments):
        """调用一个 MCP 工具并返回结果文本。"""
        ctx_tuple = self._contexts.get(server_name)
        if not ctx_tuple:
            return f"Error: server '{server_name}' not connected"
        _, session = ctx_tuple

        async def _call():
            result = await session.call_tool(tool_name, arguments)
            texts = [c.text for c in result.content if hasattr(c, "text")]
            return "\n".join(texts) if texts else "(no output)"

        try:
            return self._run_async(_call())
        except Exception as e:
            return f"MCP tool error: {e}"

    def disconnect(self) -> str:
        """断开所有 MCP 服务器连接。"""
        if not self.connected:
            return "Not connected"

        async def _cleanup():
            for name, (ctx, session) in list(self._contexts.items()):
                try:
                    await session.__aexit__(None, None, None)
                    await ctx.__aexit__(None, None, None)
                except Exception:
                    pass
            self._contexts.clear()

        try:
            self._run_async(_cleanup())
        except Exception:
            pass
        self.tools.clear()
        self.handlers.clear()
        self.connected = False
        return "MCP disconnected"

    def status(self) -> str:
        """返回当前 MCP 连接状态。"""
        if not self.connected:
            return "MCP: not connected"
        lines = [f"MCP: connected ({len(self.tools)} tools)"]
        for name in self._contexts:
            count = sum(1 for t in self.tools if t["name"].startswith(f"mcp_{name}_"))
            lines.append(f"  {name}: {count} tools")
        return "\n".join(lines)


def try_load_mcp(config_path: str):
    """尝试加载 MCP。失败时打印提示并返回 None，不会抛异常。"""
    bridge = McpBridge()
    result = bridge.connect(config_path)
    print(result)
    if bridge.connected:
        return bridge
    return None
