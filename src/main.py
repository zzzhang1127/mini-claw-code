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
from types import SimpleNamespace

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
    try:
        _mt = int(os.getenv("AGENT_MAX_TURNS", "50"))
        _mb = int(os.getenv("AGENT_MAX_BUDGET_TOKENS", "500000"))
    except ValueError:
        _mt, _mb = 50, 500_000
    sess = session_mod.Session(max_turns=_mt, max_budget_tokens=_mb)

    # Stage 4: 组装工具处理函数表
    handlers = tools_mod.build_handlers(todo, skills, task_mgr, bg, bus, team)
    extra_tools = []

    # Stage 5: 构建 system prompt
    system_prompt = (
        f"You are a coding agent at {workdir}. Use tools to solve tasks.\n"
        f"OS: {platform.platform()}. Use shell commands that exist on this OS "
        f"(e.g. Windows has no sed/awk by default).\n"
        f"Prefer read_file / edit_file / write_file over bash when editing code. "
        f"Do not re-read the same file path without reason. Avoid no-op or empty shell commands.\n"
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


def _is_tool_use_block(block) -> bool:
    if isinstance(block, dict):
        return block.get("type") == "tool_use"
    t = getattr(block, "type", None)
    if t == "tool_use":
        return True
    return getattr(t, "value", None) == "tool_use"


def _tool_use_id(block):
    if isinstance(block, dict):
        return block.get("id") or block.get("tool_call_id")
    return getattr(block, "id", None) or getattr(block, "tool_call_id", None)


def _parse_openai_tool_call(tc: dict) -> dict:
    """OpenAI 风格 tool_calls 单项 -> Anthropic 风格 dict。"""
    tid = tc.get("id")
    fn = tc.get("function")
    if isinstance(fn, dict):
        name = fn.get("name") or "tool"
        raw = fn.get("arguments") or "{}"
    else:
        name = tc.get("name") or "tool"
        raw = tc.get("arguments") or "{}"
    if isinstance(raw, str):
        try:
            inp = json.loads(raw)
        except Exception:
            inp = {}
    else:
        inp = raw if isinstance(raw, dict) else {}
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def _tool_blocks_collect(sources: list) -> list:
    """从多份 content / dump 合并所有 tool_use（去重 id）。"""
    seen = set()
    out = []

    def add_block(b):
        tid = _tool_use_id(b)
        if tid is None:
            return
        tid = str(tid)
        if tid in seen:
            return
        seen.add(tid)
        if isinstance(b, dict):
            inp = b.get("input")
            out.append(SimpleNamespace(
                type="tool_use",
                id=tid,
                name=b.get("name", "tool"),
                input=inp if isinstance(inp, dict) else {},
            ))
        else:
            inp = getattr(b, "input", None)
            out.append(SimpleNamespace(
                type="tool_use",
                id=tid,
                name=getattr(b, "name", "tool"),
                input=inp if isinstance(inp, dict) else {},
            ))

    def walk_content_list(items):
        if not isinstance(items, list):
            return
        for item in items:
            if isinstance(item, dict):
                t = item.get("type")
                if t == "tool_use":
                    add_block(item)
                elif t == "tool_calls":
                    for tc in item.get("tool_calls") or []:
                        if isinstance(tc, dict):
                            add_block(_parse_openai_tool_call(tc))
            elif _is_tool_use_block(item):
                add_block(item)

    for src in sources:
        if src is None:
            continue
        if isinstance(src, list):
            walk_content_list(src)
            continue
        try:
            dump = src.model_dump() if hasattr(src, "model_dump") else {}
        except Exception:
            dump = {}
        walk_content_list(dump.get("content"))
        for tc in dump.get("tool_calls") or []:
            if isinstance(tc, dict):
                add_block(_parse_openai_tool_call(tc))
        for b in getattr(src, "content", None) or []:
            if _is_tool_use_block(b):
                add_block(b)
    return out


def _tool_blocks_for_turn(response, assistant_content) -> list:
    """以即将写入历史的 assistant content 为准，合并 SDK + dump，避免漏并行调用。"""
    return _tool_blocks_collect([assistant_content, response])


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

        # 若网关 model_dump 里 tool 多于 SDK content，用完整 content 写回上一条 assistant
        try:
            dump = response.model_dump() if hasattr(response, "model_dump") else {}
            dcontent = dump.get("content")
            if isinstance(dcontent, list):
                def _count_tools(lst):
                    n = 0
                    for x in lst or []:
                        if not isinstance(x, dict):
                            continue
                        if x.get("type") == "tool_use":
                            n += 1
                        elif x.get("type") == "tool_calls":
                            n += len(x.get("tool_calls") or [])
                    return n

                n_dump = _count_tools(dcontent) + len(dump.get("tool_calls") or [])
                n_sdk = sum(1 for b in (response.content or []) if _is_tool_use_block(b))
                if n_dump > n_sdk:
                    session.messages[-1] = {"role": "assistant", "content": dcontent}
        except Exception:
            pass

        assistant_content = session.messages[-1]["content"]
        tool_blocks = _tool_blocks_for_turn(response, assistant_content)
        if not tool_blocks:
            for block in response.content:
                if hasattr(block, "text"):
                    cprint(block.text, "purple")
            return

        # Step 7: 工具执行
        results = []
        used_todo = False
        manual_compress = False
        for block in tool_blocks:
            name = block.name
            tid = block.id
            inp = block.input
            if name == "compress":
                manual_compress = True
            if permission.blocks(name):
                output = f"Permission denied: {name}"
            else:
                handler = handlers.get(name)
                try:
                    output = handler(**inp) if handler else f"Unknown tool: {name}"
                except Exception as e:
                    output = f"Error: {e}"
            display = str(output)
            if len(display) > 300:
                display = display[:300] + "... (truncated)"
            cprint(f"> {name}: {display}", "gray")
            results.append({"type": "tool_result", "tool_use_id": str(tid), "content": str(output)})
            if name == "TodoWrite":
                used_todo = True

        seen_ids = {str(r["tool_use_id"]) for r in results if isinstance(r, dict) and r.get("type") == "tool_result"}
        for block in tool_blocks:
            tid = str(block.id) if block.id is not None else None
            if tid is not None and tid not in seen_ids:
                results.append({"type": "tool_result", "tool_use_id": tid, "content": "Error: missing tool output (parallel parse)."})
                seen_ids.add(tid)

        # Step 8: Todo 提醒 (s03) — 放在 tool_result 之后，避免兼容网关把首条 text 与 tool 配对弄乱
        rounds_without_todo = 0 if used_todo else rounds_without_todo + 1
        if todo.has_open_items() and rounds_without_todo >= 3:
            results.append({"type": "text", "text": "<reminder>Update your todos.</reminder>"})

        session.messages.append({"role": "user", "content": results})

        # Step 9: 手动压缩 (s06)
        if manual_compress:
            print("[manual compact]")
            session.do_manual_compact()


# ── 等待所有后台工作完成 ──────────────────────────────────────

def _wait_all_done(ctx, timeout_sec=600.0):
    """等待所有队友和后台任务完成，再交还控制权给用户。"""
    team = ctx["team"]
    bg = ctx["bg"]
    deadline = time.monotonic() + timeout_sec
    while team.has_active() or bg.has_running():
        if time.monotonic() >= deadline:
            print("\033[33m[wait timeout] returning to prompt; check .team/ or running background tasks.\033[0m")
            break
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
