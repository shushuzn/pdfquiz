"""《化工原理》（第四版）题库配置：章、节、卷子规模。

build_hgyl 与 check_hgyl 共用这份配置，避免两边章号或节名对不上。
"""

from __future__ import annotations

COURSE_NAME = "化工原理"
COURSE_SUB = "第四版 · 杨祖荣主编 · 化学工业出版社"
SOURCE = "《化工原理》（第四版），杨祖荣主编，刘丽英、刘伟副主编，化学工业出版社，2021"

# 章节目录：章号 -> (标题, 起始印刷页)
CHAPTERS = {
    "ch00": ("绪论", 1),
    "ch01": ("第1章 流体流动与输送机械", 5),
    "ch02": ("第2章 非均相物系分离", 88),
    "ch03": ("第3章 传热", 116),
    "ch04": ("第4章 蒸发", 180),
    "ch05": ("第5章 气体吸收", 202),
    "ch06": ("第6章 蒸馏", 263),
    "ch07": ("第7章 固体干燥", 327),
    "ch08": ("第8章 其他分离技术", 364),
}

ORDER = list(CHAPTERS)

# 侧栏分组：每章按印刷页切成几段，(该段最后一页, 段名)
SECTIONS: dict[str, list[tuple[int, str]]] = {
    "ch00": [(4, "绪论")],
    "ch01": [
        (10, "1.1 流体物性与静力学"),
        (20, "1.3 连续性方程与机械能衡算"),
        (29, "1.4 流动型态与速度分布"),
        (41, "1.5 管路阻力"),
        (46, "1.6 管路计算"),
        (54, "1.7 流量测量"),
        (87, "1.8 流体输送机械"),
    ],
    "ch02": [
        (91, "2.1 颗粒与颗粒群特性"),
        (101, "2.2 沉降"),
        (110, "2.3 过滤"),
        (115, "2.4 过程强化与展望"),
    ],
    "ch03": [
        (126, "3.1-3.2 概述与热传导"),
        (141, "3.3 对流传热"),
        (154, "3.4 传热计算"),
        (163, "3.5 热辐射"),
        (171, "3.6 换热器"),
        (179, "3.7 强化与优化"),
    ],
    "ch04": [
        (181, "4.1 概述"),
        (192, "4.2 单效与多效计算"),
        (201, "4.4 蒸发器与附属设备"),
    ],
    "ch05": [
        (208, "5.1 概述与吸收剂"),
        (215, "5.2 相平衡与亨利定律"),
        (225, "5.3 分子扩散与对流传质"),
        (230, "5.4 双膜理论与总传质速率"),
        (247, "5.5 吸收塔计算"),
        (262, "5.6 填料塔"),
    ],
    "ch06": [
        (270, "6.1-6.2 概述与汽液平衡"),
        (281, "6.3-6.4 简单蒸馏与精馏原理"),
        (304, "6.5 精馏计算"),
        (326, "6.7-6.8 特殊精馏与板式塔"),
    ],
    "ch07": [
        (328, "7.1 概述"),
        (337, "7.2 湿空气性质与湿度图"),
        (339, "7.3 物料水分与平衡"),
        (351, "7.4-7.5 干燥计算"),
        (363, "7.6-7.7 干燥器与强化"),
    ],
    "ch08": [
        (368, "8.1 结晶"),
        (378, "8.2 吸附"),
        (394, "8.3 膜分离"),
        (425, "习题与附录"),
    ],
}

# 配额策略：题量由教材页数、节数和题型配比算出，不再逐章手改。
# 调 density 或 mix，所有章的目标一起变；新增章节只要登记页范围就自动纳入。
QUOTA = {
    "density": 1.5,  # 每印刷页目标题数
    "section_min": 8,  # 每节至少题数（习题与附录除外）
    "mix": {  # 题型配比，总和 100
        "single": 36,
        "multiple": 9,
        "truefalse": 22,
        "fill": 9,
        "short": 7,
        "term": 17,
    },
    # 页数极少的章按密度算会偏少，给知识密度保底
    "chapter_floor": {"ch00": 16, "ch04": 36},
    # 答案分布：判断题正确率区间，防止整章都是「错」而被猜中
    "answer": {"truefalse_true": (0.40, 0.60)},
}

APPENDIX = "习题与附录"
BOOK_LAST_PAGE = 425

# 单章题型上限：防止某一章塞得太满、其他章没题
MAXIMUM = {"single": 60, "multiple": 16, "truefalse": 36, "fill": 16, "short": 12, "term": 30}


def chapter_pages(stem: str) -> int:
    i = ORDER.index(stem)
    start = CHAPTERS[stem][1]
    end = CHAPTERS[ORDER[i + 1]][1] - 1 if i + 1 < len(ORDER) else BOOK_LAST_PAGE
    return end - start + 1


def sections(stem: str) -> list[str]:
    return [name for _, name in SECTIONS[stem] if name != APPENDIX]


def section_of(stem: str, page: int) -> str:
    for limit, name in SECTIONS[stem]:
        if page <= limit:
            return name
    return "未分节"


def _apportion(total: int, mix: dict[str, int]) -> dict[str, int]:
    """按配比取整，余数按最大余数法分配，并保证每种题型至少 1 题。"""
    keys = list(mix)
    exact = {k: total * mix[k] / 100 for k in keys}
    out = {k: int(exact[k]) for k in keys}
    rest = total - sum(out.values())
    ranked = sorted(keys, key=lambda k: (-(exact[k] - out[k]), keys.index(k)))
    for k in ranked[:rest]:
        out[k] += 1
    while any(out[k] == 0 for k in keys):
        zero = next(k for k in keys if out[k] == 0)
        donor = max(keys, key=lambda k: out[k])
        out[donor] -= 1
        out[zero] = 1
    return out


def _targets() -> dict[str, dict[str, int]]:
    out = {}
    for stem in ORDER:
        total = max(
            round(chapter_pages(stem) * QUOTA["density"]),
            QUOTA["chapter_floor"].get(stem, 0),
        )
        out[stem] = _apportion(total, QUOTA["mix"])
    return out


TARGETS = _targets()


def minimum(stem: str) -> dict[str, int]:
    return dict(TARGETS[stem])

SCORE = {"single": 2, "multiple": 3, "truefalse": 2, "fill": 2, "short": 8, "term": 2}
