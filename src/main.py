"""
main.py - Agent 主入口: 启动引导 + agent_loop + REPL

教学要点:
- 启动引导 (bootstrap): 加载环境 -> 创建客户端 -> 初始化各模块 -> 组装上下文
- agent_loop: 压缩管线 -> 预算检查 -> 后台通知 -> LLM 调用 -> 工具执行
- REPL: 读取用户输入 -> 斜杠命令分发 -> agent_loop 处理
- 可选 MCP: 通过 --mcp 启动参数或 /mcp 命令激活

运行方式:
  python -m src.main                       # 标准模式
  python -m src.main --mcp mcp_config.json # 带 MCP 支持

灵感来源:
- s_full.py 的 agent_loop / REPL
- claw-code/src/runtime.py 的启动引导和 turn loop
- claw-code/src/bootstrap_graph.py 的阶段化启动
"""

import json
import os
import platform
import sys
import time
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

from . import session as session_mod
from . import tools as tools_mod
from . import team as team_mod
from . import commands as cmd_mod
from .tools import get_active_tools, cprint


# ── 启动引导 (来自 claw-code/src/bootstrap_graph.py) ────────

def bootstrap():
    """启动引导: 加载环境 -> 创建客户端 -> 初始化模块 -> 组装上下文。

    返回 ctx 字典，包含所有模块实例和共享状态。
    这是整个 agent 系统的唯一入口，所有依赖在这里连接起来。
    """
    # Stage 1: 环境与客户端
    load_dotenv(override=True)
    if os.getenv("ANTHROPIC_BASE_URL"):
        os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
    workdir = Path.cwd()
    client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
    model = os.environ["MODEL_ID"]

    # Stage 2: 初始化各模块的共享依赖
    session_mod.init(client, model, workdir)
    tools_mod.init(client, model, workdir)
    team_mod.init(client, model, workdir)

    # Stage 3: 创建实例
    skills_dir = workdir / "skills"
    todo = team_mod.TodoManager()
    skills = team_mod.SkillLoader(skills_dir)
    task_mgr = team_mod.TaskManager(workdir)
    bg = team_mod.BackgroundManager(workdir)
    bus = team_mod.MessageBus(workdir)
    team = team_mod.TeammateManager(bus, task_mgr, workdir)
    permission = tools_mod.ToolPermission()
    sess = session_mod.Session()

    # Stage 4: 组装工具处理函数表
    handlers = tools_mod.build_handlers(todo, skills, task_mgr, bg, bus, team)
    extra_tools = []

    # Stage 5: 构建 system prompt
    system_prompt = (
        f"You are a coding agent at {workdir}. Use tools to solve tasks.\n"
        f"Prefer task_create/task_update/task_list for multi-step work. "
        f"Use TodoWrite for short checklists.\n"
        f"Use task for subagent delegation. Use load_skill for specialized knowledge.\n"
        f"Skills: {skills.descriptions()}"
    )

    # Stage 6: 注册斜杠命令
    cmd_mod.register_builtins()

    # Stage 7: 打印启动信息
    tool_count = len(tools_mod.TOOLS)
    cmd_count = len(cmd_mod.COMMANDS)
    print(f"Python {sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]} | {platform.platform()}")
    print(f"Model: {model} | Workdir: {workdir}")
    print(f"Tools: {tool_count} | Commands: {cmd_count} | Skills: {len(skills.skills)}")
    print(f"Session: {sess.session_id} | Budget: {sess.max_turns} turns / {sess.max_budget_tokens:,} tokens")
    print()
    sess.history.add("bootstrap", f"tools={tool_count} commands={cmd_count}")

    # Stage 8 (可选): MCP 启动参数
    mcp_bridge = None
    if "--mcp" in sys.argv:
        idx = sys.argv.index("--mcp")
        if idx + 1 < len(sys.argv):
            from .mcp_client import try_load_mcp
            mcp_bridge = try_load_mcp(sys.argv[idx + 1])
            if mcp_bridge:
                extra_tools.extend(mcp_bridge.tools)
                handlers.update(mcp_bridge.handlers)
                sess.history.add("mcp_loaded", f"{len(mcp_bridge.tools)} tools")

    ctx = {
        "client": client,
        "model": model,
        "workdir": workdir,
        "session": sess,
        "todo": todo,
        "skills": skills,
        "task_mgr": task_mgr,
        "bg": bg,
        "bus": bus,
        "team": team,
        "permission": permission,
        "handlers": handlers,
        "extra_tools": extra_tools,
        "system_prompt": system_prompt,
        "mcp": mcp_bridge,
    }
    return ctx


# ── 主 Agent 循环 ───────────────────────────────────────────

def agent_loop(ctx: dict):
    """主 agent 循环: 每一轮 = 压缩 -> 检查 -> LLM 调用 -> 工具执行。

    和 s_full.py 的 agent_loop 结构完全一致，但额外加了:
    - 预算检查 (来自 claw-code 的 query_engine)
    - 权限过滤 (来自 claw-code 的 permissions)
    - 成本追踪 (来自 claw-code 的 cost_tracker)
    """
    session = ctx["session"]
    handlers = ctx["handlers"]
    client = ctx["client"]
    model = ctx["model"]
    permission = ctx["permission"]
    todo = ctx["todo"]
    rounds_without_todo = 0

    while True:
        # Step 1: 压缩管线 (s06)
        session.do_microcompact()
        if session.should_auto_compact():
            print("[auto-compact triggered]")
            session.do_auto_compact()

        # Step 2: 预算检查 (claw-code 新增)
        if session.budget_exceeded():
            print(f"[budget exceeded: {session.cost.summary()}]")
            session.history.add("budget_exceeded", session.cost.summary())
            return

        # Step 3: 后台通知 (s08)
        notifs = ctx["bg"].drain()
        if notifs:
            txt = "\n".join(f"[bg:{n['task_id']}] {n['status']}: {n['result']}" for n in notifs)
            session.messages.append({"role": "user", "content": f"<background-results>\n{txt}\n</background-results>"})
            session.messages.append({"role": "assistant", "content": "Noted background results."})

        # Step 4: 收件箱 (s10)
        inbox = ctx["bus"].read_inbox("lead")
        if inbox:
            session.messages.append({"role": "user", "content": f"<inbox>{json.dumps(inbox, indent=2)}</inbox>"})
            session.messages.append({"role": "assistant", "content": "Noted inbox messages."})

        # Step 5: 获取当前可用工具 (权限过滤 + MCP 工具)
        active_tools = get_active_tools(permission, ctx["extra_tools"])

        # Step 6: LLM 调用（信号量限流 + 自动重试）
        from .tools import api_semaphore
        response = None
        last_err = None
        for attempt in range(3):
            try:
                with api_semaphore:
                    response = client.messages.create(
                        model=model,
                        system=ctx["system_prompt"],
                        messages=session.messages,
                        tools=active_tools,
                        max_tokens=8000,
                    )
                break
            except Exception as e:
                last_err = e
                wait = 2 ** attempt
                print(f"[API error, retry {attempt+1}/3 in {wait}s] {e}")
                time.sleep(wait)
        if response is None:
            print(f"[API failed after 3 retries, skipping turn] {last_err}")
            session.history.add("api_error", str(last_err))
            return
        session.messages.append({"role": "assistant", "content": response.content})
        session.record_turn(response.usage)

        if response.stop_reason != "tool_use":
            for block in response.content:
                if hasattr(block, "text"):
                    cprint(block.text, "purple")
            return

        # Step 7: 工具执行
        results = []
        used_todo = False
        manual_compress = False
        for block in response.content:
            if block.type == "tool_use":
                if block.name == "compress":
                    manual_compress = True
                if permission.blocks(block.name):
                    output = f"Permission denied: {block.name}"
                else:
                    handler = handlers.get(block.name)
                    try:
                        output = handler(**block.input) if handler else f"Unknown tool: {block.name}"
                    except Exception as e:
                        output = f"Error: {e}"
                display = str(output)
                if len(display) > 300:
                    display = display[:300] + "... (truncated)"
                cprint(f"> {block.name}: {display}", "gray")
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)})
                if block.name == "TodoWrite":
                    used_todo = True

        # Step 8: Todo 提醒 (s03)
        rounds_without_todo = 0 if used_todo else rounds_without_todo + 1
        if todo.has_open_items() and rounds_without_todo >= 3:
            results.insert(0, {"type": "text", "text": "<reminder>Update your todos.</reminder>"})

        session.messages.append({"role": "user", "content": results})

        # Step 9: 手动压缩 (s06)
        if manual_compress:
            print("[manual compact]")
            session.do_manual_compact()


# ── 等待所有后台工作完成 ──────────────────────────────────────

def _wait_all_done(ctx):
    """等待所有队友和后台任务完成，再交还控制权给用户。"""
    team = ctx["team"]
    bg = ctx["bg"]
    while team.has_active() or bg.has_running():
        time.sleep(0.5)


# ── REPL 入口 ───────────────────────────────────────────────

def main():
    """交互式 REPL。输入自然语言与 agent 对话，或使用 /help 查看斜杠命令。"""
    ctx = bootstrap()
    session = ctx["session"]

    while True:
        try:
            query = input("\033[36msrc >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break

        if cmd_mod.dispatch(query, ctx):
            continue

        session.add_user_message(query)
        agent_loop(ctx)
        _wait_all_done(ctx)
        print()


if __name__ == "__main__":
    main()
