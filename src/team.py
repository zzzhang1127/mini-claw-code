"""
team.py - 多 Agent 协作、任务管理、技能加载

教学要点:
- TodoManager: 待办清单跟踪 agent 工作进度 (s03)
- SkillLoader: 从 SKILL.md 文件加载专业知识 (s05)
- TaskManager: 文件级持久化任务看板，支持依赖关系 (s07)
- BackgroundManager: 后台线程执行长时间命令 (s08)
- MessageBus: 基于文件的消息传递 (s09)
- TeammateManager: 自主队友的完整生命周期 (s09/s11)

灵感来源:
- s_full.py 的 todos / skills / file_tasks / background / messaging / team
"""

import json
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path
from queue import Queue

from .tools import run_bash, run_read, run_write, run_edit, api_semaphore, get_file_lock, cprint

# 由 main.py 调用 init() 设置
_client = None
_model = None
_workdir = None

POLL_INTERVAL = 5
IDLE_TIMEOUT = 60
shutdown_requests = {}
plan_requests = {}


def init(client, model, workdir):
    """由 main.py 在启动时调用，注入共享依赖。"""
    global _client, _model, _workdir
    _client = client
    _model = model
    _workdir = workdir


# ── 待办清单 (来自 s_full.py s03) ────────────────────────────

class TodoManager:
    """简单的待办清单，用于跟踪 agent 的工作进度。
    规则: 最多 20 条，同时只能有 1 条 in_progress。"""

    def __init__(self):
        self.items = []

    def update(self, items: list) -> str:
        validated, ip = [], 0
        for i, item in enumerate(items):
            content = str(item.get("content", "")).strip()
            status = str(item.get("status", "pending")).lower()
            af = str(item.get("activeForm", "")).strip()
            if not content:
                raise ValueError(f"Item {i}: content required")
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"Item {i}: invalid status '{status}'")
            if not af:
                raise ValueError(f"Item {i}: activeForm required")
            if status == "in_progress":
                ip += 1
            validated.append({"content": content, "status": status, "activeForm": af})
        if len(validated) > 20:
            raise ValueError("Max 20 todos")
        if ip > 1:
            raise ValueError("Only one in_progress allowed")
        self.items = validated
        return self.render()

    def render(self) -> str:
        if not self.items:
            return "No todos."
        lines = []
        for item in self.items:
            m = {"completed": "[x]", "in_progress": "[>]", "pending": "[ ]"}.get(item["status"], "[?]")
            suffix = f" <- {item['activeForm']}" if item["status"] == "in_progress" else ""
            lines.append(f"{m} {item['content']}{suffix}")
        done = sum(1 for t in self.items if t["status"] == "completed")
        lines.append(f"\n({done}/{len(self.items)} completed)")
        return "\n".join(lines)

    def has_open_items(self) -> bool:
        return any(item.get("status") != "completed" for item in self.items)


# ── 技能加载 (来自 s_full.py s05) ────────────────────────────

class SkillLoader:
    """扫描 skills/ 目录下的 SKILL.md 文件，为 agent 提供专业知识。
    SKILL.md 格式: YAML frontmatter (---name/description---) + Markdown body。"""

    def __init__(self, skills_dir: Path):
        self.skills = {}
        if skills_dir.exists():
            for f in sorted(skills_dir.rglob("SKILL.md")):
                text = f.read_text()
                match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
                meta, body = {}, text
                if match:
                    for line in match.group(1).strip().splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            meta[k.strip()] = v.strip()
                    body = match.group(2).strip()
                name = meta.get("name", f.parent.name)
                self.skills[name] = {"meta": meta, "body": body}

    def descriptions(self) -> str:
        if not self.skills:
            return "(no skills)"
        return "\n".join(f"  - {n}: {s['meta'].get('description', '-')}" for n, s in self.skills.items())

    def load(self, name: str) -> str:
        s = self.skills.get(name)
        if not s:
            return f"Error: Unknown skill '{name}'. Available: {', '.join(self.skills.keys())}"
        return f"<skill name=\"{name}\">\n{s['body']}\n</skill>"


# ── 文件级任务管理 (来自 s_full.py s07) ──────────────────────

class TaskManager:
    """持久化的任务看板，每个任务保存为独立 JSON 文件。
    支持: 创建、查询、更新状态、依赖阻塞、认领。"""

    def __init__(self, workdir: Path):
        self.tasks_dir = workdir / ".tasks"
        self.tasks_dir.mkdir(exist_ok=True)

    def _next_id(self) -> int:
        ids = [int(f.stem.split("_")[1]) for f in self.tasks_dir.glob("task_*.json")]
        return max(ids, default=0) + 1

    def _load(self, tid: int) -> dict:
        p = self.tasks_dir / f"task_{tid}.json"
        if not p.exists():
            raise ValueError(f"Task {tid} not found")
        return json.loads(p.read_text())

    def _save(self, task: dict):
        (self.tasks_dir / f"task_{task['id']}.json").write_text(json.dumps(task, indent=2))

    def create(self, subject: str, description: str = "") -> str:
        task = {"id": self._next_id(), "subject": subject, "description": description,
                "status": "pending", "owner": None, "blockedBy": [], "blocks": []}
        self._save(task)
        return json.dumps(task, indent=2)

    def get(self, tid: int) -> str:
        return json.dumps(self._load(tid), indent=2)

    def update(self, tid: int, status: str = None,
               add_blocked_by: list = None, add_blocks: list = None) -> str:
        task = self._load(tid)
        if status:
            task["status"] = status
            if status == "completed":
                for f in self.tasks_dir.glob("task_*.json"):
                    t = json.loads(f.read_text())
                    if tid in t.get("blockedBy", []):
                        t["blockedBy"].remove(tid)
                        self._save(t)
            if status == "deleted":
                (self.tasks_dir / f"task_{tid}.json").unlink(missing_ok=True)
                return f"Task {tid} deleted"
        if add_blocked_by:
            task["blockedBy"] = list(set(task["blockedBy"] + add_blocked_by))
        if add_blocks:
            task["blocks"] = list(set(task["blocks"] + add_blocks))
        self._save(task)
        return json.dumps(task, indent=2)

    def list_all(self) -> str:
        tasks = [json.loads(f.read_text()) for f in sorted(self.tasks_dir.glob("task_*.json"))]
        if not tasks:
            return "No tasks."
        lines = []
        for t in tasks:
            m = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}.get(t["status"], "[?]")
            owner = f" @{t['owner']}" if t.get("owner") else ""
            blocked = f" (blocked by: {t['blockedBy']})" if t.get("blockedBy") else ""
            lines.append(f"{m} #{t['id']}: {t['subject']}{owner}{blocked}")
        return "\n".join(lines)

    def claim(self, tid: int, owner: str) -> str:
        task = self._load(tid)
        task["owner"] = owner
        task["status"] = "in_progress"
        self._save(task)
        return f"Claimed task #{tid} for {owner}"


# ── 后台任务 (来自 s_full.py s08) ────────────────────────────

class BackgroundManager:
    """在后台线程中运行命令，完成后通过通知队列告知主循环。"""

    def __init__(self, workdir: Path):
        self.workdir = workdir
        self.tasks = {}
        self.notifications = Queue()

    def run(self, command: str, timeout: int = 120) -> str:
        tid = str(uuid.uuid4())[:8]
        self.tasks[tid] = {"status": "running", "command": command, "result": None}
        threading.Thread(target=self._exec, args=(tid, command, timeout), daemon=True).start()
        return f"Background task {tid} started: {command[:80]}"

    def _exec(self, tid: str, command: str, timeout: int):
        try:
            r = subprocess.run(command, shell=True, cwd=self.workdir,
                               capture_output=True, text=True, timeout=timeout)
            output = (r.stdout + r.stderr).strip()[:50000]
            self.tasks[tid].update({"status": "completed", "result": output or "(no output)"})
        except Exception as e:
            self.tasks[tid].update({"status": "error", "result": str(e)})
        self.notifications.put({"task_id": tid, "status": self.tasks[tid]["status"],
                                "result": self.tasks[tid]["result"][:500]})

    def check(self, tid: str = None) -> str:
        if tid:
            t = self.tasks.get(tid)
            return f"[{t['status']}] {t.get('result', '(running)')}" if t else f"Unknown: {tid}"
        return "\n".join(f"{k}: [{v['status']}] {v['command'][:60]}" for k, v in self.tasks.items()) or "No bg tasks."

    def drain(self) -> list:
        notifs = []
        while not self.notifications.empty():
            notifs.append(self.notifications.get_nowait())
        return notifs

    def has_running(self) -> bool:
        return any(t["status"] == "running" for t in self.tasks.values())


# ── 消息总线 (来自 s_full.py s09) ────────────────────────────

class MessageBus:
    """基于文件的消息传递系统，让 agent 和队友之间通信。
    每个成员有独立的 .jsonl 收件箱文件。"""

    def __init__(self, workdir: Path):
        self.inbox_dir = workdir / ".team" / "inbox"
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    def send(self, sender: str, to: str, content: str,
             msg_type: str = "message", extra: dict = None) -> str:
        msg = {"type": msg_type, "from": sender, "content": content,
               "timestamp": time.time()}
        if extra:
            msg.update(extra)
        path = self.inbox_dir / f"{to}.jsonl"
        with get_file_lock(str(path)):
            with open(path, "a") as f:
                f.write(json.dumps(msg) + "\n")
        return f"Sent {msg_type} to {to}"

    def read_inbox(self, name: str) -> list:
        path = self.inbox_dir / f"{name}.jsonl"
        with get_file_lock(str(path)):
            if not path.exists():
                return []
            msgs = [json.loads(line) for line in path.read_text().strip().splitlines() if line]
            path.write_text("")
        return msgs

    def broadcast(self, sender: str, content: str, names: list) -> str:
        count = 0
        for n in names:
            if n != sender:
                self.send(sender, n, content, "broadcast")
                count += 1
        return f"Broadcast to {count} teammates"


# ── 队友管理 (来自 s_full.py s09/s11) ────────────────────────

class TeammateManager:
    """管理自主队友的生命周期: 生成 -> 工作 -> 空闲 -> 自动认领任务。
    每个队友在独立线程中运行自己的 agent loop。"""

    def __init__(self, bus: MessageBus, task_mgr: TaskManager, workdir: Path):
        self.team_dir = workdir / ".team"
        self.team_dir.mkdir(exist_ok=True)
        self.bus = bus
        self.task_mgr = task_mgr
        self.workdir = workdir
        self.config_path = self.team_dir / "config.json"
        self.config = self._load_config()

    def _load_config(self) -> dict:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text())
        return {"team_name": "default", "members": []}

    def _save_config(self):
        self.config_path.write_text(json.dumps(self.config, indent=2))

    def _find(self, name: str) -> dict:
        for m in self.config["members"]:
            if m["name"] == name:
                return m
        return None

    def spawn(self, name: str, role: str, prompt: str) -> str:
        member = self._find(name)
        if member:
            if member["status"] not in ("idle", "shutdown"):
                return f"Error: '{name}' is currently {member['status']}"
            member["status"] = "working"
            member["role"] = role
        else:
            member = {"name": name, "role": role, "status": "working"}
            self.config["members"].append(member)
        self._save_config()
        threading.Thread(target=self._loop, args=(name, role, prompt), daemon=True).start()
        return f"Spawned '{name}' (role: {role})"

    def _set_status(self, name: str, status: str):
        member = self._find(name)
        if member:
            member["status"] = status
            self._save_config()

    def _loop(self, name: str, role: str, prompt: str):
        """队友的独立 agent loop，在后台线程中运行。"""
        team_name = self.config["team_name"]
        sys_prompt = (f"You are '{name}', role: {role}, team: {team_name}, at {self.workdir}. "
                      f"Use idle when done with current work. You may auto-claim tasks.")
        messages = [{"role": "user", "content": prompt}]
        tools = [
            {"name": "bash", "description": "Run command.", "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
            {"name": "read_file", "description": "Read file.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
            {"name": "write_file", "description": "Write file.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
            {"name": "edit_file", "description": "Edit file.", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
            {"name": "send_message", "description": "Send message.", "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "content": {"type": "string"}}, "required": ["to", "content"]}},
            {"name": "idle", "description": "Signal no more work.", "input_schema": {"type": "object", "properties": {}}},
            {"name": "claim_task", "description": "Claim task by ID.", "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}},
        ]
        dispatch = {
            "bash": lambda **kw: run_bash(kw["command"]),
            "read_file": lambda **kw: run_read(kw["path"]),
            "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
            "edit_file": lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
        }
        while True:
            # -- 工作阶段 --
            for _ in range(50):
                inbox = self.bus.read_inbox(name)
                for msg in inbox:
                    if msg.get("type") == "shutdown_request":
                        self._set_status(name, "shutdown")
                        return
                    messages.append({"role": "user", "content": json.dumps(msg)})
                try:
                    with api_semaphore:
                        response = _client.messages.create(
                            model=_model, system=sys_prompt, messages=messages,
                            tools=tools, max_tokens=8000)
                except Exception as e:
                    cprint(f"API error: {str(e)[:100]}", "gray", f"  [{name}] ")
                    self._set_status(name, "shutdown")
                    return
                messages.append({"role": "assistant", "content": response.content})
                if response.stop_reason != "tool_use":
                    break
                results = []
                idle_requested = False
                for block in response.content:
                    if block.type == "tool_use":
                        if block.name == "idle":
                            idle_requested = True
                            output = "Entering idle phase."
                        elif block.name == "claim_task":
                            output = self.task_mgr.claim(block.input["task_id"], name)
                        elif block.name == "send_message":
                            output = self.bus.send(name, block.input["to"], block.input["content"])
                        else:
                            handler = dispatch.get(block.name, lambda **kw: "Unknown")
                            output = handler(**block.input)
                        cprint(f"{block.name}: {str(output)[:120]}", "gray", f"  [{name}] ")
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)})
                messages.append({"role": "user", "content": results})
                if idle_requested:
                    break
            # -- 空闲阶段: 轮询消息和未认领任务 --
            self._set_status(name, "idle")
            resume = False
            for _ in range(IDLE_TIMEOUT // max(POLL_INTERVAL, 1)):
                time.sleep(POLL_INTERVAL)
                inbox = self.bus.read_inbox(name)
                if inbox:
                    for msg in inbox:
                        if msg.get("type") == "shutdown_request":
                            self._set_status(name, "shutdown")
                            return
                        messages.append({"role": "user", "content": json.dumps(msg)})
                    resume = True
                    break
                unclaimed = []
                for f in sorted(self.task_mgr.tasks_dir.glob("task_*.json")):
                    t = json.loads(f.read_text())
                    if t.get("status") == "pending" and not t.get("owner") and not t.get("blockedBy"):
                        unclaimed.append(t)
                if unclaimed:
                    task = unclaimed[0]
                    self.task_mgr.claim(task["id"], name)
                    if len(messages) <= 3:
                        messages.insert(0, {"role": "user", "content":
                            f"<identity>You are '{name}', role: {role}, team: {team_name}.</identity>"})
                        messages.insert(1, {"role": "assistant", "content": f"I am {name}. Continuing."})
                    messages.append({"role": "user", "content":
                        f"<auto-claimed>Task #{task['id']}: {task['subject']}\n{task.get('description', '')}</auto-claimed>"})
                    messages.append({"role": "assistant", "content": f"Claimed task #{task['id']}. Working on it."})
                    resume = True
                    break
            if not resume:
                self._set_status(name, "shutdown")
                return
            self._set_status(name, "working")

    def list_all(self) -> str:
        if not self.config["members"]:
            return "No teammates."
        lines = [f"Team: {self.config['team_name']}"]
        for m in self.config["members"]:
            lines.append(f"  {m['name']} ({m['role']}): {m['status']}")
        return "\n".join(lines)

    def member_names(self) -> list:
        return [m["name"] for m in self.config["members"]]

    def has_active(self) -> bool:
        return any(m["status"] == "working" for m in self.config["members"])

    def handle_shutdown(self, teammate: str) -> str:
        """向队友发送关闭请求 (s10)。"""
        req_id = str(uuid.uuid4())[:8]
        shutdown_requests[req_id] = {"target": teammate, "status": "pending"}
        self.bus.send("lead", teammate, "Please shut down.", "shutdown_request", {"request_id": req_id})
        return f"Shutdown request {req_id} sent to '{teammate}'"

    def handle_plan_review(self, request_id: str, approve: bool, feedback: str = "") -> str:
        """审批队友提交的计划 (s10)。"""
        req = plan_requests.get(request_id)
        if not req:
            return f"Error: Unknown plan request_id '{request_id}'"
        req["status"] = "approved" if approve else "rejected"
        self.bus.send("lead", req["from"], feedback, "plan_approval_response",
                     {"request_id": request_id, "approve": approve, "feedback": feedback})
        return f"Plan {req['status']} for '{req['from']}'"
