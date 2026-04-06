"""
session.py - 会话管理、压缩、持久化、成本追踪

教学要点:
- 会话引擎: 管理多轮对话的消息列表、轮次计数、token 预算
- 上下文压缩: microcompact (清理旧 tool_result) + auto_compact (LLM 摘要)
- 会话持久化: 将对话保存为 JSON，支持后续恢复
- 成本追踪: 记录每轮的 input/output token 用量

灵感来源:
- s_full.py 的 estimate_tokens / microcompact / auto_compact
- claw-code/src/query_engine.py 的 Session 概念和预算控制
- claw-code/src/session_store.py 的持久化
- claw-code/src/cost_tracker.py 的成本追踪
- claw-code/src/history.py 的事件日志
"""

import json
import time
import uuid
from pathlib import Path

# 由 main.py 调用 init() 设置
_client = None
_model = None
_workdir = None
_transcript_dir = None
TOKEN_THRESHOLD = 100_000


def init(client, model, workdir):
    """由 main.py 在启动时调用，注入共享依赖。"""
    global _client, _model, _workdir, _transcript_dir
    _client = client
    _model = model
    _workdir = workdir
    _transcript_dir = workdir / ".transcripts"


# ── Token 估算与压缩 (来自 s_full.py s06) ───────────────────

def estimate_tokens(messages: list) -> int:
    """粗略估算消息列表的 token 数 (字符数 / 4)。"""
    return len(json.dumps(messages, default=str)) // 4


def microcompact(messages: list):
    """清理旧的 tool_result 内容，只保留最近 3 条。
    这是一个轻量级压缩，不调用 LLM。"""
    tool_results = []
    for msg in messages:
        if msg["role"] == "user" and isinstance(msg.get("content"), list):
            for part in msg["content"]:
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    tool_results.append(part)
    if len(tool_results) <= 3:
        return
    for part in tool_results[:-3]:
        if isinstance(part.get("content"), str) and len(part["content"]) > 100:
            part["content"] = "[cleared]"


def auto_compact(messages: list) -> list:
    """用 LLM 对整段对话生成摘要，替换原始消息。
    压缩前将完整对话保存到 .transcripts/ 目录。"""
    _transcript_dir.mkdir(exist_ok=True)
    path = _transcript_dir / f"transcript_{int(time.time())}.jsonl"
    with open(path, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=str) + "\n")
    conv_text = json.dumps(messages, default=str)[:80000]
    resp = _client.messages.create(
        model=_model,
        messages=[{"role": "user", "content": f"Summarize for continuity:\n{conv_text}"}],
        max_tokens=2000,
    )
    summary = resp.content[0].text
    return [
        {"role": "user", "content": f"[Compressed. Transcript: {path}]\n{summary}"},
        {"role": "assistant", "content": "Understood. Continuing with summary context."},
    ]


# ── 成本追踪 (来自 claw-code/src/cost_tracker.py) ───────────

class CostTracker:
    """记录每次 LLM 调用的 token 用量。"""

    def __init__(self):
        self.total_input = 0
        self.total_output = 0
        self.turns = 0
        self.events = []

    def record(self, input_tokens: int, output_tokens: int):
        self.total_input += input_tokens
        self.total_output += output_tokens
        self.turns += 1
        self.events.append(f"turn {self.turns}: in={input_tokens} out={output_tokens}")

    def summary(self) -> str:
        return (f"Turns: {self.turns} | "
                f"Input: {self.total_input} tokens | "
                f"Output: {self.total_output} tokens | "
                f"Total: {self.total_input + self.total_output} tokens")


# ── 事件日志 (来自 claw-code/src/history.py) ─────────────────

class HistoryLog:
    """记录会话中的关键事件，方便调试和回顾。"""

    def __init__(self):
        self.events = []

    def add(self, title: str, detail: str):
        self.events.append({"title": title, "detail": detail, "time": time.time()})

    def show(self) -> str:
        if not self.events:
            return "No history events."
        lines = ["Session History:"]
        for e in self.events:
            lines.append(f"  [{e['title']}] {e['detail']}")
        return "\n".join(lines)


# ── 会话类 (来自 claw-code/src/query_engine.py) ──────────────

class Session:
    """管理一次完整的对话会话。

    整合了消息列表、轮次计数、token 预算、成本追踪、事件日志。
    支持持久化保存和恢复。
    """

    def __init__(self, max_turns=100, max_budget_tokens=500_000):
        self.session_id = uuid.uuid4().hex[:12]
        self.messages = []
        self.max_turns = max_turns
        self.max_budget_tokens = max_budget_tokens
        self.turn_count = 0
        self.cost = CostTracker()
        self.history = HistoryLog()
        self.history.add("session_start", f"id={self.session_id}")

    def add_user_message(self, content):
        self.messages.append({"role": "user", "content": content})

    def record_turn(self, usage):
        """记录一次 LLM 调用的用量。usage 是 response.usage 对象。"""
        inp = getattr(usage, "input_tokens", 0)
        out = getattr(usage, "output_tokens", 0)
        self.cost.record(inp, out)
        self.turn_count += 1

    def budget_exceeded(self) -> bool:
        """检查是否超出轮次或 token 预算。"""
        if self.turn_count >= self.max_turns:
            return True
        total = self.cost.total_input + self.cost.total_output
        return total >= self.max_budget_tokens

    def should_auto_compact(self) -> bool:
        return estimate_tokens(self.messages) > TOKEN_THRESHOLD

    def do_microcompact(self):
        microcompact(self.messages)

    def do_auto_compact(self):
        self.messages[:] = auto_compact(self.messages)
        self.history.add("auto_compact", f"turn={self.turn_count}")

    def do_manual_compact(self) -> bool:
        if self.messages:
            self.messages[:] = auto_compact(self.messages)
            self.history.add("manual_compact", f"turn={self.turn_count}")
            return True
        return False

    # ── 持久化 (来自 claw-code/src/session_store.py) ──

    def save(self, directory=None) -> str:
        """保存会话到 JSON 文件，返回文件路径。"""
        save_dir = Path(directory) if directory else _workdir / ".sessions"
        save_dir.mkdir(parents=True, exist_ok=True)
        path = save_dir / f"{self.session_id}.json"
        data = {
            "session_id": self.session_id,
            "messages": self.messages,
            "turn_count": self.turn_count,
            "input_tokens": self.cost.total_input,
            "output_tokens": self.cost.total_output,
        }
        path.write_text(json.dumps(data, indent=2, default=str))
        self.history.add("session_saved", str(path))
        return str(path)

    @classmethod
    def load(cls, session_id: str, directory=None) -> "Session":
        """从 JSON 文件恢复会话。"""
        load_dir = Path(directory) if directory else _workdir / ".sessions"
        path = load_dir / f"{session_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")
        data = json.loads(path.read_text())
        session = cls()
        session.session_id = data["session_id"]
        session.messages = data["messages"]
        session.turn_count = data.get("turn_count", 0)
        session.cost.total_input = data.get("input_tokens", 0)
        session.cost.total_output = data.get("output_tokens", 0)
        session.history.add("session_loaded", f"id={session_id}")
        return session
