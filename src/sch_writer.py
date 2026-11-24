# -*- coding: utf-8 -*-
"""把连接关系 JSON 变成 KiCad 8 能打开的原理图（.kicad_sch）。

技术路线（KiCad 8 没有原理图 Python API，只能手写 S-expression）：
  1. 从本机 KiCad 自带的符号库里抽出用到的符号定义，塞进 lib_symbols；
  2. 按网格摆放符号；
  3. 每个引脚向外拉一小段导线，在末端挂一个「网络标签」。
     同名标签在 KiCad 里自动视为同一个网络，所以不需要布线算法，
     电气连接完全正确，只是不好看 —— 自动生成的图都这样。

关键坐标陷阱：符号库用 Y 轴向上，原理图文件用 Y 轴向下，
所以从库坐标转到图纸坐标时 Y 要取反。
"""
from __future__ import annotations

import math
import re
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import kicad_env

KICAD_FORMAT_VERSION = "20230819"  # KiCad 8.0 原理图格式版本
GRID_MM = 38.1  # 1.5 英寸，保证落在 1.27mm 栅格上
STUB_MM = 2.54  # 引脚外接短线长度


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------- S 表达式
def _find_block(text: str, start: int) -> str:
    """从 start（指向 '(' 的位置）开始，返回配对完整的整段文本。"""
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("括号不配对，符号库文件可能损坏")


def _tokenize(s: str) -> List[str]:
    tokens: List[str] = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if ch.isspace():
            i += 1
        elif ch in "()":
            tokens.append(ch)
            i += 1
        elif ch == '"':
            j = i + 1
            buf = []
            while j < n:
                if s[j] == "\\" and j + 1 < n:
                    buf.append(s[j + 1])
                    j += 2
                elif s[j] == '"':
                    break
                else:
                    buf.append(s[j])
                    j += 1
            tokens.append('"' + "".join(buf) + '"')
            i = j + 1
        else:
            j = i
            while j < n and not s[j].isspace() and s[j] not in "()":
                j += 1
            tokens.append(s[i:j])
            i = j
    return tokens


def _parse(tokens: List[str]) -> list:
    stack: List[list] = [[]]
    for tok in tokens:
        if tok == "(":
            new: list = []
            stack[-1].append(new)
            stack.append(new)
        elif tok == ")":
            stack.pop()
        else:
            stack[-1].append(tok)
    return stack[0][0] if stack[0] else []


def _unquote(tok: str) -> str:
    return tok[1:-1] if isinstance(tok, str) and tok.startswith('"') else tok


def _find_all(node: list, key: str) -> List[list]:
    out = []
    if isinstance(node, list):
        if node and node[0] == key:
            out.append(node)
        for child in node:
            out.extend(_find_all(child, key))
    return out


# ------------------------------------------------------------- 符号库访问
class SymbolLibrary:
    def __init__(self, symbols_dir: Path):
        self.dir = symbols_dir
        self._cache: Dict[str, str] = {}

    def names(self, lib: str) -> List[str]:
        """列出某个库文件里所有顶级符号名。"""
        path = self.dir / ("%s.kicad_sym" % lib)
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
        # 顶级符号定义恰好缩进一个制表符，子单元缩进更多
        return re.findall(r'^\t\(symbol\s+"([^"]+)"', text, re.M)

    def suggest(self, lib_id: str) -> Optional[str]:
        """给出最接近的真实符号名，用于修正 LLM 编造的名字。"""
        import difflib

        if ":" not in lib_id:
            return None
        lib, name = lib_id.split(":", 1)
        candidates = self.names(lib)
        if not candidates:
            return None
        match = difflib.get_close_matches(name, candidates, n=1, cutoff=0.5)
        return "%s:%s" % (lib, match[0]) if match else None

    def block(self, lib_id: str, _depth: int = 0) -> Optional[str]:
        """返回符号定义原文（已把名字改成 'Lib:Name'）。

        KiCad 库里大量符号用 (extends "父符号") 继承父级的图形和引脚，
        自己只覆盖几个属性。原理图文件里必须存「拍平」后的完整定义，
        所以这里递归取父级，再把名字改成本符号。
        """
        if lib_id in self._cache:
            return self._cache[lib_id]
        if ":" not in lib_id or _depth > 4:
            return None
        lib, name = lib_id.split(":", 1)
        path = self.dir / ("%s.kicad_sym" % lib)
        if not path.exists():
            return None

        text = path.read_text(encoding="utf-8", errors="replace")
        # 顶级符号定义形如 (symbol "Name" ...)，缩进一个制表符
        pattern = re.compile(r'^\t\(symbol\s+"%s"' % re.escape(name), re.M)
        match = pattern.search(text)
        if not match:
            return None
        block = _find_block(text, match.start())
        block = block.replace('(symbol "%s"' % name, '(symbol "%s"' % lib_id, 1)

        parent = re.search(r'\(extends\s+"([^"]+)"\)', block)
        if parent:
            parent_name = parent.group(1)
            parent_block = self.block("%s:%s" % (lib, parent_name), _depth + 1)
            if not parent_block:
                return None
            # 父级定义已改名为 Lib:Parent，这里再改成 Lib:Child，
            # 同时把子单元名 Parent_1_1 改成 Child_1_1，
            # 否则 KiCad 认不出这些子单元属于哪个符号
            parent_block = parent_block.replace(
                '(symbol "%s:%s"' % (lib, parent_name), '(symbol "%s"' % lib_id, 1
            )
            parent_block = re.sub(
                r'"%s_(\d+_\d+)"' % re.escape(parent_name), r'"%s_\1"' % name, parent_block
            )
            block = parent_block

        self._cache[lib_id] = block
        return block

    def pins(self, lib_id: str) -> Dict[str, Tuple[float, float, int]]:
        """返回 {引脚号: (x, y, 角度)}，坐标是符号库坐标（Y 向上）。"""
        block = self.block(lib_id)
        if not block:
            return {}
        tree = _parse(_tokenize(block))
        result: Dict[str, Tuple[float, float, int]] = {}
        for pin in _find_all(tree, "pin"):
            at = next((c for c in pin if isinstance(c, list) and c and c[0] == "at"), None)
            num = next((c for c in pin if isinstance(c, list) and c and c[0] == "number"), None)
            if not at or not num:
                continue
            try:
                x, y, angle = float(at[1]), float(at[2]), int(float(at[3]))
            except (IndexError, ValueError):
                continue
            result[_unquote(num[1])] = (x, y, angle)
        return result


def locate_symbols_dir() -> Optional[Path]:
    root = kicad_env.find_kicad_root()
    if not root:
        return None
    for rel in ("share/kicad/symbols", "share/kicad/library"):
        candidate = root / rel
        if candidate.is_dir():
            return candidate
    return None


# --------------------------------------------------------------- 生成原理图
def _fmt(v: float) -> str:
    s = "%.4f" % v
    s = s.rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _dir(angle: int) -> Tuple[float, float]:
    a = angle % 360
    return {0: (1.0, 0.0), 90: (0.0, 1.0), 180: (-1.0, 0.0), 270: (0.0, -1.0)}.get(a, (0.0, 0.0))


def build_schematic(netlist: dict, project_name: str = "pcb-agent") -> Tuple[str, List[str]]:
    """返回 (原理图文本, 警告列表)。"""
    warnings: List[str] = []
    symbols_dir = locate_symbols_dir()
    if not symbols_dir:
        raise RuntimeError(
            "找不到 KiCad 符号库目录（<KiCad>/share/kicad/symbols）。先装 KiCad 8。"
        )
    lib = SymbolLibrary(symbols_dir)

    rooted = _uid()
    components = netlist.get("components", [])
    pin_map = {c["ref"]: c.get("pins", {}) for c in components}

    # 网格布局：4 列
    cols = 4
    placed = {}
    lib_blocks: Dict[str, str] = {}
    symbol_chunks: List[str] = []
    wire_chunks: List[str] = []
    label_chunks: List[str] = []
    pin_abs: Dict[Tuple[str, str], Tuple[float, float, int]] = {}

    for idx, comp in enumerate(components):
        ref = comp["ref"]
        lib_id = comp.get("symbol") or ""
        block = lib.block(lib_id) if lib_id else None
        if not block:
            hint = lib.suggest(lib_id) if lib_id else None
            if hint:
                warnings.append(
                    "%s 的符号 %s 库里没有，最接近的是 %s —— 改 netlist 的 symbol 字段"
                    % (ref, lib_id, hint)
                )
            else:
                warnings.append("%s 的符号 %s 库里没有，且找不到相似项，已跳过" % (ref, lib_id))
            continue
        lib_blocks[lib_id] = block

        col, row = idx % cols, idx // cols
        sx = 50.0 + col * GRID_MM
        sy = 40.0 + row * GRID_MM
        placed[ref] = (sx, sy)

        pins = lib.pins(lib_id)
        sym_uuid = _uid()
        value = str(comp.get("value", "")).replace('"', "")
        footprint = str(comp.get("footprint", "")).replace('"', "")
        symbol_chunks.append(
            "\n".join(
                [
                    '  (symbol (lib_id "%s") (at %s %s 0) (unit 1)'
                    % (lib_id, _fmt(sx), _fmt(sy)),
                    "    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)",
                    "    (uuid %s)" % sym_uuid,
                    '    (property "Reference" "%s" (at %s %s 0)'
                    % (ref, _fmt(sx), _fmt(sy - 6.5)),
                    "      (effects (font (size 1.27 1.27)))",
                    "    )",
                    '    (property "Value" "%s" (at %s %s 0)' % (value, _fmt(sx), _fmt(sy + 6.5)),
                    "      (effects (font (size 1.27 1.27)))",
                    "    )",
                    '    (property "Footprint" "%s" (at %s %s 0)'
                    % (footprint, _fmt(sx), _fmt(sy)),
                    "      (effects (font (size 1.27 1.27)) hide)",
                    "    )",
                    '    (property "Datasheet" "~" (at %s %s 0)' % (_fmt(sx), _fmt(sy)),
                    "      (effects (font (size 1.27 1.27)) hide)",
                    "    )",
                    '    (property "Description" "" (at %s %s 0)' % (_fmt(sx), _fmt(sy)),
                    "      (effects (font (size 1.27 1.27)) hide)",
                    "    )",
                    "".join('    (pin "%s" (uuid %s))\n' % (p, _uid()) for p in pins).rstrip("\n"),
                    "    (instances",
                    '      (project "%s"' % project_name,
                    '        (path "/%s"' % rooted,
                    '          (reference "%s") (unit 1)' % ref,
                    "        )",
                    "      )",
                    "    )",
                    "  )",
                ]
            )
        )

        for pin_no, (px, py, angle) in pins.items():
            # 库坐标 -> 图纸坐标：Y 取反
            ax, ay = sx + px, sy - py
            dx, dy = _dir(angle + 180)
            ex, ey = sx + px + dx * STUB_MM, sy - (py + dy * STUB_MM)
            pin_abs[(ref, pin_no)] = (ax, ay, angle)
            wire_chunks.append(
                "  (wire (pts (xy %s %s) (xy %s %s))\n"
                "    (stroke (width 0) (type solid))\n"
                "    (uuid %s)\n  )"
                % (_fmt(ax), _fmt(ay), _fmt(ex), _fmt(ey), _uid())
            )
            # 标签挂在短线末端
            pin_abs[(ref, pin_no)] = (ex, ey, angle)

    # 每个网络：给所有成员引脚挂同名标签
    for net in netlist.get("nets", []):
        name = net.get("name", "")
        if not name:
            continue
        for node in net.get("nodes", []):
            key = (str(node.get("ref")), str(node.get("pin")))
            if key not in pin_abs:
                warnings.append("网络 %s 的引脚 %s.%s 未在图上找到" % (name, key[0], key[1]))
                continue
            ex, ey, angle = pin_abs[key]
            # 标签朝外摆放
            just = "left" if angle in (0, 270) else "right"
            label_chunks.append(
                '  (label "%s" (at %s %s 0) (fields_autoplaced)\n'
                "    (effects (font (size 1.27 1.27)) (justify %s bottom))\n"
                "    (uuid %s)\n  )"
                % (name, _fmt(ex), _fmt(ey), just, _uid())
            )

    parts = [
        "(kicad_sch (version %s) (generator eeschema)" % KICAD_FORMAT_VERSION,
        "",
        "  (uuid %s)" % rooted,
        "",
        '  (paper "A3")',
        "",
        "  (lib_symbols",
        "\n\n".join(lib_blocks.values()),
        "  )",
        "",
        "\n\n".join(symbol_chunks),
        "",
        "\n".join(wire_chunks),
        "",
        "\n".join(label_chunks),
        "",
        "  (sheet_instances",
        '    (path "/" (page "1"))',
        "  )",
        ")",
        "",
    ]
    return "\n".join(parts), warnings


def netlist_to_file(netlist: dict, out_path: Path, project_name: str = "pcb-agent") -> List[str]:
    text, warnings = build_schematic(netlist, project_name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    return warnings
