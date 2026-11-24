# AI Agent 电路板设计

输入一句自然语言（例如「帮我设计一块 Arduino 最小系统板」），由 Agent 产出 **BOM 元器件清单 → 引脚级连接关系（JSON）→ KiCad 可打开的原理图**。

> 课程大作业项目仓库。当前进度：**W1 环境搭建 + 脚手架**。

---

## 环境要求

| 组件 | 版本 | 说明 |
|---|---|---|
| Python | >= 3.10 | 已用 3.13 验证，3.10 / 3.11 / 3.12 亦可 |
| KiCad | 8.x | 原理图 / PCB 生成载体；自带独立 Python（含 `pcbnew`） |
| LLM API | OpenAI 兼容接口 | 课程统一密钥，或用学校算力平台 |
| Git | 任意较新版本 | 过程分依据，每周必须有 commit |

## 5 分钟跑起来

> 第一次接触 GitHub / KiCad / 电路？先看 **[docs/zero-to-week1.md](docs/zero-to-week1.md)**，那里是从零开始的手把手版本。

```bash
# 1. 建虚拟环境（别用系统 Python）
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# Windows CMD / Git Bash
.venv\Scripts\activate

# 2. 装依赖
pip install -r requirements.txt

# 3. 配置
cp .env.example .env
#   然后用编辑器打开 .env，填 LLM_API_KEY 和 TEMPLATE_DIR

# 4. 自检（这一步会告诉你还差什么）
python scripts/env_check.py

# 5. 验证 KiCad 脚本接口
python scripts/hello_kicad.py
```

`env_check.py` 全部显示 `[ OK ]`、`hello_kicad.py` 在 `out/` 下生成 `_smoke.kicad_pcb`，就说明**第一周里程碑「脚手架跑通」达成**。

## 完整链路（已跑通）

```bash
# 1. 一句话需求 -> BOM + 连接关系 JSON + 报告
python scripts/mvp.py --mock                          # 无密钥时先用 mock 跑通
python scripts/mvp.py "帮我设计一块 Arduino 最小系统板"   # 有密钥时真实调用

# 2. 连接关系 JSON -> KiCad 原理图
python scripts/netlist_to_sch.py out/arduino_min_system_netlist.json

# 3. 对账：让 KiCad 自己反导网表，逐网络比对
python scripts/verify_sch.py out/arduino_min_system_netlist.json out/arduino_min_system.kicad_sch

# 4. 看一眼成品
kicad-cli sch export pdf --output out/board.pdf out/arduino_min_system.kicad_sch

# 5. 一句话改设计，重新生成（双击 一键改参数.bat 也可以）
python scripts/revise.py "把 C1 和 C2 换成 18pF"
python scripts/revise.py "把 R2 换成 470"
python scripts/revise.py "删除 C5"
```

第 3 步通过（`全部一致`）就等于证明了：**KiCad 认定的连接关系和你给的 JSON 完全相同**。

原理图用「网络标签」连接：每个引脚外拉 2.54mm 短线、末端挂同名标签，
所以无需布线算法，电气上完全正确，只是排版不好看——自动生成的图都这样。

## 三种运行方式

| 入口 | 什么时候用 | 需要什么 |
|---|---|---|
| **`一键全自动.bat`** | 有 API 密钥，或本机跑了 Ollama | 一个程序能直连的模型接口 |
| **`一键运行.bat`** | 只有网页版模型 | 手动复制粘贴中转 |
| **`一键改参数.bat`** | 任何时候都能用 | 不需要模型 |

全自动的配置方法见 **[docs/auto-mode.md](docs/auto-mode.md)**（含本机 Ollama 完全离线方案）。

## 没有 API 密钥怎么办

三条路，按推荐程度排：

**路线 A：人工中转（推荐，模型真实参与）**

双击项目根目录的 **`一键运行.bat`**（或在命令行执行 `python scripts/offline_run.py`）。

脚本会分两步生成 Prompt 文件，你复制到任意网页版大模型（山大 AI 助手 / DeepSeek / 通义 / Kimi），
把回复存成 `out/offline/step1_reply.json`、`step2_reply.json`，脚本接着校验、出图、自动对账。
**模型是真的在干活，只是传输靠人手复制**——报告里如实写明即可。

**路线 B：内置模板（纯程序，作为离线兜底）**

```bash
python scripts/mvp.py --mock
```

不调用任何模型，直接用 `data/sample_netlist.json`。用于证明下游链路可用。
**报告里必须注明这是模板数据，不是模型输出。**

**路线 C：本地小模型**

装 Ollama 跑 Qwen 1.5B 之类。理论上完整，但 7B 以下的模型输出稳定 JSON 的能力很差，
配合 `src/llm.py` 的重试闭环才勉强能用。赶时间不推荐。

## 目录结构

```
pcb-agent/
├── 一键运行.bat             # 双击运行完整流水线（无需命令行）
├── 一键改参数.bat           # 双击做第 5 步：一句话改设计
├── 一键上传.bat             # 双击提交到 GitHub（无需命令行）
├── deliverables/            # 交付物：设计报告、原理图 PDF/KiCad、BOM
├── src/
│   ├── settings.py          # 读取 .env 配置
│   └── kicad_env.py         # 探测 KiCad 安装路径、自带 Python、pcbnew
├── scripts/
│   ├── env_check.py         # 环境自检（W1 核心工具）
│   ├── hello_kicad.py       # KiCad 接口连通性测试
│   ├── mvp.py               # 一句话需求 -> BOM -> 连接关系 JSON
│   ├── check_netlist.py     # 连接关系 JSON 结构校验
│   ├── netlist_to_sch.py    # 连接关系 JSON -> KiCad 原理图
│   ├── verify_sch.py        # 原理图对账（反导网表逐网络比对）
│   └── revise.py            # 第 5 步：一句话改设计并重新生成
├── docs/
│   ├── zero-to-week1.md     # 零基础完全手册（GitHub / 电路常识 / KiCad 手把手）
│   ├── week1-checklist.md   # 第一周任务清单与验收标准
│   └── kicad-crash-course.md# KiCad 概念速成 + 五个坑
├── data/
│   ├── arduino_min_system_bom.csv    # 参考 BOM（认知用，非标准答案）
│   └── sample_netlist.json           # W3 目标输出格式样例
├── out/                     # 运行产物，已 gitignore
└── .env                     # 本地密钥配置，已 gitignore
```

## 8 周路线（来自课程宣讲）

| 周次 | 内容 | 里程碑 |
|---|---|---|
| W1 | 背景学习 + 环境搭建 | 脚手架跑通 |
| W2 | Agent 原理入门（Prompt + 工具调用） | 会写工具调用 |
| W3–W4 | 最小原型 MVP：自然语言 → BOM + 连接表 → JSON | MVP 演示 |
| W5–W6 | KiCad 集成：JSON → 真实原理图 + 改需求 | 原理图生成 |
| W7 | 迭代优化 + DRC 闭环 | 闭环通过 |
| W8 | 报告与答辩 | 正式交付 |

## 常见问题

**Q：`env_check.py` 报 KiCad 未找到，但我装了。**
装在非默认路径时，把 `KICAD_HOME` 指到带版本号的那一层，例如 `D:\KiCad\8.0`（该目录下应有 `bin\kicad-cli.exe`）。

**Q：`hello_kicad.py` 说当前解释器没有 `pcbnew`。**
正常现象。KiCad 自带独立 Python，脚本会自动改用 `KiCad\8.0\bin\python.exe` 重新执行，不需要你手动切换。

**Q：原理图能用 Python 直接生成吗？**
KiCad 8 **没有**官方 eeschema Python API（`pcbnew` 只管 PCB）。可行路线是直接生成 `.kicad_sch`（S-expression 文本），或使用 `kicad-skip` 这类第三方库。这一点务必先和课程模板的实现方式对齐。

**Q：控制台中文乱码。**
用 Windows Terminal 或 VS Code 内置终端；CMD 里先执行 `chcp 65001`。
