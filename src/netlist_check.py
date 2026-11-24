# -*- coding: utf-8 -*-
"""把网表结构校验逻辑抽成模块，供脚本和流水线共用。"""
from __future__ import annotations


POWER_NETS = {"VCC", "VDD", "GND", "VSS", "+5V", "+3V3", "5V", "3V3"}


def repair(data: dict) -> list:
    """修复「一个引脚被塞进多个网络」这类硬伤。

    规则：优先保留电源网络（去耦电容的另一端几乎总是 GND）；
    否则保留引脚数最多的那个网络。每一步都会记录，绝不悄悄改。
    """
    notes = []
    owner = {}
    for net in data.get("nets", []):
        for node in net.get("nodes", []):
            key = (str(node.get("ref")), str(node.get("pin")))
            owner.setdefault(key, []).append(net)

    for key, nets in owner.items():
        if len(nets) < 2:
            continue
        names = [n.get("name", "?") for n in nets]
        power = [n for n in nets if str(n.get("name", "")).upper() in POWER_NETS]
        if len(power) == 1:
            keep = power[0]
            why = "优先保留电源网络"
        else:
            keep = max(nets, key=lambda n: len(n.get("nodes", [])))
            why = "保留引脚更多的网络"
        for net in nets:
            if net is keep:
                continue
            net["nodes"] = [
                n
                for n in net.get("nodes", [])
                if (str(n.get("ref")), str(n.get("pin"))) != key
            ]
        notes.append(
            "引脚 %s.%s 同时在 %s 里，%s：保留 %s，从 %s 移除"
            % (
                key[0],
                key[1],
                " / ".join(names),
                why,
                keep.get("name"),
                " / ".join(n for n in names if n != keep.get("name")),
            )
        )

    # 只剩一个引脚的网络等于悬空，删掉（KiCad 里会显示成未连接）
    before = len(data.get("nets", []))
    data["nets"] = [n for n in data.get("nets", []) if len(n.get("nodes", [])) >= 2]
    dropped = before - len(data["nets"])
    if dropped:
        notes.append("删除了 %d 个只剩单个引脚的网络（等于悬空）" % dropped)
    return notes


def validate(data: dict) -> tuple:
    """返回 (errors, warnings) 两个列表。空 errors 即结构合法。"""
    errors = []
    warnings = []

    if not isinstance(data, dict):
        return ["顶层必须是 JSON 对象 {}".format("{}")], warnings

    for key in ("schema_version", "board", "components", "nets"):
        if key not in data:
            errors.append("缺少顶层字段：%s" % key)
    if errors:
        return errors, warnings

    components = data["components"]
    if not isinstance(components, list) or not components:
        return ["components 必须是非空数组"], warnings

    pins_by_ref = {}
    for i, comp in enumerate(components):
        where = "components[%d]" % i
        if not isinstance(comp, dict):
            errors.append("%s 不是对象" % where)
            continue
        for field in ("ref", "value", "symbol", "footprint", "pins"):
            if field not in comp:
                errors.append("%s 缺少字段 %s" % (where, field))
        ref = comp.get("ref")
        if not ref:
            continue
        if ref in pins_by_ref:
            errors.append("位号重复：%s（同一块板上位号必须唯一）" % ref)
        pins = comp.get("pins") or {}
        if not isinstance(pins, dict) or not pins:
            errors.append(
                '%s（%s）的 pins 为空或格式不对，需要 {"引脚号": "引脚名"}' % (where, ref)
            )
            pins = {}
        pins_by_ref[ref] = set(str(p) for p in pins.keys())

    nets = data["nets"]
    if not isinstance(nets, list) or not nets:
        return errors + ["nets 必须是非空数组"], warnings

    used_pins = set()
    pin_owner = {}
    seen_names = set()
    for j, net in enumerate(nets):
        where = "nets[%d]" % j
        if not isinstance(net, dict):
            errors.append("%s 不是对象" % where)
            continue
        name = net.get("name")
        if not name:
            errors.append("%s 缺少 name" % where)
            name = "<未命名>"
        elif name in seen_names:
            errors.append("网络名重复：%s" % name)
        seen_names.add(name)

        nodes = net.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            errors.append("%s（%s）的 nodes 为空" % (where, name))
            continue
        if len(nodes) < 2:
            warnings.append("网络 %s 只连了 1 个引脚，实际等于悬空" % name)

        for node in nodes:
            ref = str(node.get("ref", ""))
            pin = str(node.get("pin", ""))
            if ref not in pins_by_ref:
                errors.append("网络 %s 引用了不存在的位号：%s" % (name, ref))
                continue
            if pin not in pins_by_ref[ref]:
                errors.append("网络 %s 引用了 %s 上不存在的引脚：%s" % (name, ref, pin))
                continue
            key = (ref, pin)
            if key in pin_owner and pin_owner[key] != name:
                errors.append(
                    "引脚 %s.%s 同时出现在网络 %s 和 %s —— 一个引脚只能属于一个网络"
                    % (ref, pin, pin_owner[key], name)
                )
            else:
                pin_owner[key] = name
            used_pins.add(key)

    for ref, pins in pins_by_ref.items():
        dangling = sorted(pins - {p for r, p in used_pins if r == ref})
        if dangling:
            warnings.append(
                "器件 %s 有未接入任何网络的引脚：%s" % (ref, ", ".join(dangling))
            )

    return errors, warnings
