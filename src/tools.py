"""
tools.py - 工具定义、处理函数、权限控制

教学要点:
- 基础工具: bash, read_file, write_file, edit_file (文件操作沙箱)
- 子代理: 用独立的 LLM 会话处理隔离任务
- 权限系统: 按名称或前缀屏蔽危险工具 (来自 claw-code)
- 工具注册: TOOLS (schema) + build_handlers (执行) 的双表设计

灵感来源:
- s_full.py 的 base_tools / subagent / tool_dispatch
- claw-code/src/permissions.py 的权限过滤
- claw-code/src/tools.py 的 filter/permission 机制
"""

import json
import subprocess
import threading
from pathlib import Path

# 由 main.py 调用 init() 设置
_client = None
_model = None
_workdir = None
api_semaphore = threading.Semaphore(3)  # 全局 API 并发限制，默认 3
print_lock = threading.Lock()
_file_locks = {}
_file_locks_guard = threading.Lock()

COLORS = {"gray": "\033[90m", "purple": "\033[35m", "cyan": "\033[36m", "reset": "\033[0m"}


def get_file_lock(path: str) -> threading.Lock:
    """获取指定文件路径的锁，不存在则创建。"""
    key = str(Path(path).resolve())
    with _file_locks_guard:
        if key not in _file_locks:
            _file_locks[key] = threading.Lock()
        return _file_locks[key]


def cprint(text: str, color: str = "", prefix: str = ""):
    """线程安全的彩色输出。"""
    line = f"{prefix}{text}" if prefix else text
    with print_lock:
        if color in COLORS:
            print(f"{COLORS[color]}{line}{COLORS['reset']}")
        else:
            print(line)


def init(client, model, workdir, max_concurrency=3):
    """由 main.py 在启动时调用，注入共享依赖。"""
    global _client, _model, _workdir, api_semaphore
    _client = client
    _model = model
    _workdir = workdir
    api_semaphore = threading.Semaphore(max_concurrency)


# ── 路径安全 ─────────────────────────────────────────────────

def safe_path(p: str) -> Path:
    """确保路径不会逃逸出工作目录。"""
    path = (_workdir / p).resolve()
    if not path.is_relative_to(_workdir):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


# ── 基础工具 (来自 s_full.py) ────────────────────────────────

def run_bash(command: str) -> str:
    """执行 shell 命令，屏蔽危险操作。"""
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=_workdir,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        if not out:
            return "(no output)"
        if len(out) > 50000:
            return out[:50000] + "\n... (truncated)"
        return out
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"


def run_read(path: str, limit: int = None) -> str:
    """读取文件内容，可选行数限制。"""
    try:
        lines = safe_path(path).read_text(encoding="utf-8").splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"


def run_write(path: str, content: str) -> str:
    """写入文件，自动创建父目录。"""
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        with get_file_lock(str(fp)):
            fp.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    """精确替换文件中的文本 (只替换第一次出现)。"""
    try:
        fp = safe_path(path)
        with get_file_lock(str(fp)):
            c = fp.read_text(encoding="utf-8")
            if old_text not in c:
                return f"Error: Text not found in {path}"
            fp.write_text(c.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


# ── 子代理 (来自 s_full.py s04) ──────────────────────────────

def run_subagent(prompt: str, agent_type: str = "Explore") -> str:
    """启动一个独立的子代理来处理隔离任务。
    Explore 模式只有只读工具，general-purpose 模式可以写文件。"""
    sub_tools = [
        {"name": "bash", "description": "Run command.",
         "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
        {"name": "read_file", "description": "Read file.",
         "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    ]
    if agent_type != "Explore":
        sub_tools += [
            {"name": "write_file", "description": "Write file.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
            {"name": "edit_file", "description": "Edit file.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
        ]
    sub_handlers = {
        "bash": lambda **kw: run_bash(kw["command"]),
        "read_file": lambda **kw: run_read(kw["path"]),
        "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
        "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
    }
    sub_msgs = [{"role": "user", "content": prompt}]
    resp = None
    for _ in range(30):
        resp = _client.messages.create(model=_model, messages=sub_msgs, tools=sub_tools, max_tokens=8000)
        sub_msgs.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            break
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                h = sub_handlers.get(b.name, lambda **kw: "Unknown tool")
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": str(h(**b.input))[:50000]})
        sub_msgs.append({"role": "user", "content": results})
    if resp:
        return "".join(b.text for b in resp.content if hasattr(b, "text")) or "(no summary)"
    return "(subagent failed)"


# ── 工具权限 (来自 claw-code/src/permissions.py) ─────────────

class ToolPermission:
    """按名称或前缀屏蔽工具。

    例如: deny("bash") 会禁止 bash 工具,
          deny_prefix("mcp_") 会禁止所有 MCP 工具。
    """

    def __init__(self):
        self.deny_names = set()
        self.deny_prefixes = []

    def deny(self, name: str):
        self.deny_names.add(name.lower())

    def allow(self, name: str):
        self.deny_names.discard(name.lower())

    def deny_prefix(self, prefix: str):
        if prefix.lower() not in self.deny_prefixes:
            self.deny_prefixes.append(prefix.lower())

    def blocks(self, name: str) -> bool:
        low = name.lower()
        if low in self.deny_names:
            return True
        return any(low.startswith(p) for p in self.deny_prefixes)

    def status(self) -> str:
        if not self.deny_names and not self.deny_prefixes:
            return "All tools allowed."
        lines = ["Blocked tools:"]
        for n in sorted(self.deny_names):
            lines.append(f"  - {n}")
        for p in self.deny_prefixes:
            lines.append(f"  - {p}* (prefix)")
        return "\n".join(lines)


# ── 工具 Schema 定义 (来自 s_full.py) ────────────────────────

VALID_MSG_TYPES = {"message", "broadcast", "shutdown_request",
                   "shutdown_response", "plan_approval_response"}

TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "TodoWrite", "description": "Update task tracking list.",
     "input_schema": {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {"content": {"type": "string"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}, "activeForm": {"type": "string"}}, "required": ["content", "status", "activeForm"]}}}, "required": ["items"]}},
    {"name": "task", "description": "Spawn a subagent for isolated exploration or work.",
     "input_schema": {"type": "object", "properties": {"prompt": {"type": "string"}, "agent_type": {"type": "string", "enum": ["Explore", "general-purpose"]}}, "required": ["prompt"]}},
    {"name": "load_skill", "description": "Load specialized knowledge by name.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "compress", "description": "Manually compress conversation context.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "background_run", "description": "Run command in background thread.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["command"]}},
    {"name": "check_background", "description": "Check background task status.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "string"}}}},
    {"name": "task_create", "description": "Create a persistent file task.",
     "input_schema": {"type": "object", "properties": {"subject": {"type": "string"}, "description": {"type": "string"}}, "required": ["subject"]}},
    {"name": "task_get", "description": "Get task details by ID.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}},
    {"name": "task_update", "description": "Update task status or dependencies.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "deleted"]}, "add_blocked_by": {"type": "array", "items": {"type": "integer"}}, "add_blocks": {"type": "array", "items": {"type": "integer"}}}, "required": ["task_id"]}},
    {"name": "task_list", "description": "List all tasks.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "spawn_teammate", "description": "Spawn a persistent autonomous teammate.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "role": {"type": "string"}, "prompt": {"type": "string"}}, "required": ["name", "role", "prompt"]}},
    {"name": "list_teammates", "description": "List all teammates.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "send_message", "description": "Send a message to a teammate.",
     "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "content": {"type": "string"}, "msg_type": {"type": "string", "enum": list(VALID_MSG_TYPES)}}, "required": ["to", "content"]}},
    {"name": "read_inbox", "description": "Read and drain the lead's inbox.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "broadcast", "description": "Send message to all teammates.",
     "input_schema": {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}},
    {"name": "shutdown_request", "description": "Request a teammate to shut down.",
     "input_schema": {"type": "object", "properties": {"teammate": {"type": "string"}}, "required": ["teammate"]}},
    {"name": "plan_approval", "description": "Approve or reject a teammate's plan.",
     "input_schema": {"type": "object", "properties": {"request_id": {"type": "string"}, "approve": {"type": "boolean"}, "feedback": {"type": "string"}}, "required": ["request_id", "approve"]}},
    {"name": "idle", "description": "Enter idle state.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "claim_task", "description": "Claim a task from the board.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}},
]


# ── 组装处理函数表 ───────────────────────────────────────────

def build_handlers(todo, skills, task_mgr, bg, bus, team):
    """组装工具名 -> 处理函数的映射表。由 main.py 在初始化后调用。"""
    return {
        "bash":             lambda **kw: run_bash(kw["command"]),
        "read_file":        lambda **kw: run_read(kw["path"], kw.get("limit")),
        "write_file":       lambda **kw: run_write(kw["path"], kw["content"]),
        "edit_file":        lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
        "TodoWrite":        lambda **kw: todo.update(kw["items"]),
        "task":             lambda **kw: run_subagent(kw["prompt"], kw.get("agent_type", "Explore")),
        "load_skill":       lambda **kw: skills.load(kw["name"]),
        "compress":         lambda **kw: "Compressing...",
        "background_run":   lambda **kw: bg.run(kw["command"], kw.get("timeout", 120)),
        "check_background": lambda **kw: bg.check(kw.get("task_id")),
        "task_create":      lambda **kw: task_mgr.create(kw["subject"], kw.get("description", "")),
        "task_get":         lambda **kw: task_mgr.get(kw["task_id"]),
        "task_update":      lambda **kw: task_mgr.update(kw["task_id"], kw.get("status"), kw.get("add_blocked_by"), kw.get("add_blocks")),
        "task_list":        lambda **kw: task_mgr.list_all(),
        "spawn_teammate":   lambda **kw: team.spawn(kw["name"], kw["role"], kw["prompt"]),
        "list_teammates":   lambda **kw: team.list_all(),
        "send_message":     lambda **kw: bus.send("lead", kw["to"], kw["content"], kw.get("msg_type", "message")),
        "read_inbox":       lambda **kw: json.dumps(bus.read_inbox("lead"), indent=2),
        "broadcast":        lambda **kw: bus.broadcast("lead", kw["content"], team.member_names()),
        "shutdown_request": lambda **kw: team.handle_shutdown(kw["teammate"]),
        "plan_approval":    lambda **kw: team.handle_plan_review(kw["request_id"], kw["approve"], kw.get("feedback", "")),
        "idle":             lambda **kw: "Lead does not idle.",
        "claim_task":       lambda **kw: task_mgr.claim(kw["task_id"], "lead"),
    }


def get_active_tools(permission: ToolPermission = None, extra_tools: list = None) -> list:
    """返回当前可用的工具列表，根据权限过滤，合并额外工具 (如 MCP)。"""
    tools = list(TOOLS)
    if extra_tools:
        tools.extend(extra_tools)
    if permission:
        tools = [t for t in tools if not permission.blocks(t["name"])]
    return tools
