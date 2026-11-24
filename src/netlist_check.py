# -*- coding: utf-8 -*-
"""把网表结构校验逻辑抽成模块，供脚本和流水线共用。"""
from __future__ import annotations


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
            used_pins.add((ref, pin))

    for ref, pins in pins_by_ref.items():
        dangling = sorted(pins - {p for r, p in used_pins if r == ref})
        if dangling:
            warnings.append(
                "器件 %s 有未接入任何网络的引脚：%s" % (ref, ", ".join(dangling))
            )

    return errors, warnings
