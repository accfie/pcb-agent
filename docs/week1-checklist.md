# 第一周任务清单

> 目标只有一个：**脚手架跑通**。
> 不是学会画板，不是写好 Prompt，是把环境铺平、让模板在自己机器上跑起来。
>
> **零基础先读 [`zero-to-week1.md`](zero-to-week1.md)** —— GitHub 注册、电路七个概念、KiCad 手把手都在里面。

## 一、必做项（本周必须全绿）

### 1. 装环境

- [ ] **Python 3.10+ 虚拟环境**：项目根目录下 `python -m venv .venv`，激活后再 `pip install -r requirements.txt`
      - 注意：不要用系统 Python 直接装包，后面依赖一多必然打架
- [ ] **KiCad 8.0.8**（不是官网首页的最新版！）：https://mirrors.aliyun.com/kicad/windows/stable/kicad-8.0.8-x86_64.exe
      - 组件里把 Symbols / Footprints / 3D Models 都勾上
      - 版本必须与课程一致，否则你存出的原理图助教的 KiCad 8 打不开
- [ ] **LLM API 密钥**：课程群领取，填进 `.env`；没有的话走学校算力平台备用通道
- [ ] **Git**：配置身份，建仓库

```bash
git config --global user.name "你的名字"
git config --global user.email "你的邮箱"
git init
```

### 2. 跑通自检

- [ ] `python scripts/env_check.py` —— 0 项 `[FAIL]`
- [ ] `python scripts/hello_kicad.py` —— `out/` 下生成 `_smoke.kicad_pcb`

### 3. 拉模板、跑通模板

- [ ] 从课程群下载**课程模板工程**和**示例库**，解压到 `D:\study\人工智能基础\电路板设计\course-template`
- [ ] 把绝对路径填进 `.env` 的 `TEMPLATE_DIR`
- [ ] 用 KiCad 打开模板工程，确认能正常显示
- [ ] 按模板自带说明跑一遍，确认默认示例能出结果
- [ ] **卡住的地方记进下面的「踩坑记录」**，这是答辩时的素材

### 4. 认识 KiCad（约 1–2 小时）

- [ ] 通读 `docs/kicad-crash-course.md`
- [ ] 手动打开示例工程，点开一个元件，看它的**符号名 / 封装名 / 引脚编号**
- [ ] 用 KiCad 的「工具 → 生成网表」，导出一份网表文件，打开看看长什么样
- [ ] 想清楚一件事：**Agent 最终要生成的那个文件，格式到底长什么样**

### 5. 留下痕迹

- [ ] 完成第一次 commit

```bash
git add .
git commit -m "W1: 环境搭建与脚手架，env_check 全绿"
```

## 二、验收标准（自查用）

用自己的话回答得出，才算真的完成：

1. 项目里 `src/settings.py` 和 `src/kicad_env.py` 各自负责什么？
2. 为什么 `pcbnew` 只有在 KiCad 自带的 Python 里才能 import？
3. KiCad 8 的原理图能靠 Python API 直接生成吗？不能的话，替代路线是什么？
4. 一块板从「一句话需求」到「KiCad 能打开的原理图」，中间经过哪几个文件？
5. 你的 `.env` 为什么不能提交到 Git？

## 三、踩坑记录

> 边做边填。答辩时"我踩过哪些坑、怎么解决的"比"我做完了"值钱得多。

| 时间 | 现象 | 原因 | 解决 |
|---|---|---|---|
| | | | |

## 四、本周不要做的事

- 不要提前写 Agent 主逻辑（W2 才到）
- 不要碰进阶挑战（先拿满基础 40 分）
- 不要一开始就选复杂电路，**目标板锁定 Arduino 最小系统板**
- 不要为了"看起来完整"而写一堆空函数——`pass` 比假实现诚实
