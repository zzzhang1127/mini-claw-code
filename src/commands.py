"""
commands.py - 斜杠命令注册表

教学要点:
- 命令注册表模式: 将 REPL 中硬编码的 if/elif 抽象为可扩展的注册表
- 每个命令是一个 (arg, ctx) -> None 的函数，ctx 提供所有共享状态
- 新增命令只需 register() 一行，不用修改分发逻辑

灵感来源:
- s_full.py 的 /compact /tasks /team /inbox
- claw-code/src/commands.py 的注册/查找/执行模式
"""

import json

COMMANDS = {}


def register(name, handler, help_text=""):
    """注册一个斜杠命令。"""
    COMMANDS[name] = {"handler": handler, "help": help_text}


def dispatch(query: str, ctx: dict) -> bool:
    """处理斜杠命令。返回 True 表示已处理，False 表示不是斜杠命令。"""
    parts = query.strip().split(maxsplit=1)
    if not parts or not parts[0].startswith("/"):
        return False
    cmd = parts[0]
    arg = parts[1] if len(parts) > 1 else ""
    entry = COMMANDS.get(cmd)
    if not entry:
        print(f"Unknown command: {cmd}. Type /help for list.")
        return True
    entry["handler"](arg, ctx)
    return True


# ── 内置命令 ─────────────────────────────────────────────────

def cmd_help(arg, ctx):
    """列出所有可用的斜杠命令。"""
    print("Available commands:")
    for name, entry in sorted(COMMANDS.items()):
        print(f"  {name:20s} {entry['help']}")


def cmd_compact(arg, ctx):
    """手动压缩对话上下文。"""
    if ctx["session"].do_manual_compact():
        print("[manual compact done]")
    else:
        print("Nothing to compact.")


def cmd_tasks(arg, ctx):
    """列出所有持久化任务。"""
    print(ctx["task_mgr"].list_all())


def cmd_team(arg, ctx):
    """列出所有队友的状态。"""
    print(ctx["team"].list_all())


def cmd_inbox(arg, ctx):
    """读取并清空 lead 的收件箱。"""
    msgs = ctx["bus"].read_inbox("lead")
    print(json.dumps(msgs, indent=2))


def cmd_cost(arg, ctx):
    """显示累计 token 用量 (来自 claw-code 的成本追踪概念)。"""
    print(ctx["session"].cost.summary())


def cmd_history(arg, ctx):
    """显示本次会话的关键事件日志 (来自 claw-code 的 history 概念)。"""
    print(ctx["session"].history.show())


def cmd_session(arg, ctx):
    """会话管理: 查看状态、保存、恢复 (来自 claw-code 的 session_store 概念)。
    用法: /session | /session save | /session load <id>"""
    parts = arg.strip().split(maxsplit=1)
    if not parts:
        s = ctx["session"]
        print(f"Session: {s.session_id}")
        print(f"Turns: {s.turn_count} / {s.max_turns}")
        print(s.cost.summary())
        return
    action = parts[0]
    if action == "save":
        path = ctx["session"].save()
        print(f"Session saved to {path}")
    elif action == "load":
        if len(parts) < 2:
            print("Usage: /session load <session_id>")
            return
        try:
            from .session import Session
            loaded = Session.load(parts[1])
            ctx["session"] = loaded
            print(f"Loaded session {parts[1]} ({loaded.turn_count} turns)")
        except FileNotFoundError as e:
            print(f"Error: {e}")
    else:
        print("Usage: /session [save | load <id>]")


def cmd_permissions(arg, ctx):
    """查看或设置工具权限 (来自 claw-code 的 permissions 概念)。
    用法: /permissions | /permissions deny <name> | /permissions allow <name>"""
    perm = ctx["permission"]
    parts = arg.strip().split()
    if not parts:
        print(perm.status())
        return
    action = parts[0]
    if action == "deny" and len(parts) > 1:
        perm.deny(parts[1])
        print(f"Denied: {parts[1]}")
    elif action == "allow" and len(parts) > 1:
        perm.allow(parts[1])
        print(f"Allowed: {parts[1]}")
    else:
        print("Usage: /permissions [deny <name> | allow <name>]")


def cmd_mcp(arg, ctx):
    """MCP 控制 (实验性，默认关闭)。
    用法: /mcp enable <config.json> | /mcp disable | /mcp status"""
    mcp = ctx.get("mcp")
    parts = arg.strip().split(maxsplit=1)
    if not parts:
        if mcp and mcp.connected:
            print(mcp.status())
        else:
            print("MCP: not connected. Use /mcp enable <config.json>")
        return
    action = parts[0]
    if action == "enable":
        if len(parts) < 2:
            print("Usage: /mcp enable <config.json>")
            return
        from .mcp_client import try_load_mcp
        bridge = try_load_mcp(parts[1])
        if bridge:
            ctx["mcp"] = bridge
            ctx["extra_tools"].extend(bridge.tools)
            ctx["handlers"].update(bridge.handlers)
    elif action == "disable":
        if mcp:
            mcp.disconnect()
            ctx["extra_tools"][:] = [t for t in ctx["extra_tools"] if not t["name"].startswith("mcp_")]
            for key in list(ctx["handlers"].keys()):
                if key.startswith("mcp_"):
                    del ctx["handlers"][key]
            ctx["mcp"] = None
            print("MCP disconnected.")
        else:
            print("MCP not connected.")
    elif action == "status":
        print(mcp.status() if mcp else "MCP: not connected.")
    else:
        print("Usage: /mcp [enable <config.json> | disable | status]")


def register_builtins():
    """注册所有内置斜杠命令。在 main.py 启动时调用一次。"""
    register("/help",        cmd_help,        "Show this help")
    register("/compact",     cmd_compact,     "Manually compress conversation context")
    register("/tasks",       cmd_tasks,       "List all persistent tasks")
    register("/team",        cmd_team,        "List all teammates")
    register("/inbox",       cmd_inbox,       "Read the lead's inbox")
    register("/cost",        cmd_cost,        "Show token usage and cost")
    register("/history",     cmd_history,     "Show session event log")
    register("/session",     cmd_session,     "Session management [save | load <id>]")
    register("/permissions", cmd_permissions, "Tool permissions [deny/allow <name>]")
    register("/mcp",         cmd_mcp,         "MCP control [enable <config> | disable | status]")
