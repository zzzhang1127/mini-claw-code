# mini-claw-code

[English](./README.md) | **中文**

模块化 Agent Harness（`src/`）+ 上游同款 `skills/`。

本仓库是 [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) 的**精简发布**：只包含可运行的 **`src/`** 模块化 Harness，以及沿用上游目录结构的 **`skills/`**（通过 `load_skill` 按需加载 `SKILL.md`）。

除上述来源外，命名与整体设计还**借鉴**了 [ultraworkers/claw-code](https://github.com/ultraworkers/claw-code)（公开的 Rust 版 `claw` CLI Agent 框架）。本仓库**并非** claw-code 的移植，而是在延续 learn-claude-code 脉络的同时，对 claw-code 的思路予以致谢与对齐。

**本仓库实际包含的内容：**

| 路径 | 说明 |
|------|------|
| **`src/`** | 主入口、工具调度、会话与压缩、团队与消息总线、斜杠命令、可选实验性 MCP 客户端等。 |
| **`skills/`** | 示例技能包（`SKILL.md`），与上游技能加载方式一致。 |
| 根目录 | `README.md`、`README-zh.md`、`LICENSE`、`requirements.txt`、`.env.example`、`.gitignore`。 |

**本仓库不包含**（需要请到上游仓库获取）：

- `agents/`（s01–s12 渐进脚本与 `s_full.py`）
- `docs/`（课程文档）
- `web/`（Next.js 学习站点）

完整学习路径见上游：**[shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)**。

## `src/` 功能概览

- **模块拆分**：启动引导、主循环与 REPL、工具表、会话引擎、团队协作、命令注册表、可选 MCP。
- **会话**：轮次与 Token 预算、用量统计、工具结果轻量裁剪与自动/手动摘要压缩、会话 JSON 存取。
- **运行时工具策略**：按名称或前缀屏蔽工具；REPL 中 `/permissions` 调整。
- **并发与安全**：工作区写文件与收件箱使用文件锁；全局 API 信号量减轻主代理与多队友同时请求时的限流。
- **终端体验**：工具输出与最终回答分色；队友输出带名字前缀；一轮用户任务后可在适当时机等待队友/后台命令结束再出现下一行 `src >>`。
- **工程细节**：Windows 下文件读写 UTF-8；API 失败重试；根据响应中是否含 **`tool_use` 块**决定是否执行工具，兼容非完全 Anthropic 语义的网关。
- **可选 MCP（默认关闭）**：`--mcp` 或 `/mcp`，需额外安装 `mcp`、`httpx`。

## 安装依赖

```bash
pip install -r requirements.txt
```

**仅在使用 MCP 时：**

```bash
pip install mcp httpx
```

## 配置

```bash
cp .env.example .env
```

至少填写 `ANTHROPIC_API_KEY`（或兼容网关的 Key）与 `MODEL_ID`。可选：`ANTHROPIC_BASE_URL`。

## 运行

```bash
python -m src.main
```

启用 MCP：

```bash
python -m src.main --mcp path/to/mcp_config.json
```

REPL 中输入 `/help` 查看斜杠命令。

## 许可证

MIT（与上游一致）。
