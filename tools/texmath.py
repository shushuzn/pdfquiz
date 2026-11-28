"""把转写下来的线性公式文本转成 LaTeX，供页面用 KaTeX 渲染。

数据里公式原本是 `u_{1} = q_{V}/((π/4)d_{1}^{2}) = 1.75 m/s` 这种线性写法，
直接丢给 KaTeX 会因为 π、×、−、√、° 这些字符报错。本模块只做「安全」的
机械转换：能整段映射成 LaTeX 就转，遇到认不出的字符就放弃、保留原线性文本，
所以最坏情况只是这一处仍按纯文本显示，不会渲染出错的公式。

入口是 convert_line()，它把一行拆成交替的文本片段与公式片段。
"""

from __future__ import annotations

import re

# 中日韩文字与全角标点：出现即认为这一行不是「纯公式」
_CJK = r"\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uff00-\uffef"
CJK = re.compile("[" + _CJK + "]")
# 混排行里可以试着转公式的候选：连续的非中文片段。
# 下标里允许夹中文（教材写了 H_{g允}、Σh_{f吸入}），所以把 _{…}、^{…} 整组当成一个字符，
# 免得在花的里面被切开、前后各剩半条公式。
SCRIPT_GROUP = r"[_^]\{[^{}]*\}"
LATIN_RUN = re.compile("(?:" + SCRIPT_GROUP + "|[^" + _CJK + "])+")

MATHY_CHARS = "=≈_√Σ′″°×·≤≥∝±∞→" + "".join(
    "αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΥΦΨΩ"
)
MATHY = re.compile("[" + re.escape(MATHY_CHARS) + r"]|[A-Za-z}\s]\^\{")

# 少数常见化学式：整词包成直立体，免得 NH_{3} 排成三个斜体变量相乘
CHEM = {
    "NH_{3}": r"\mathrm{NH}_{3}",
    "CO_{2}": r"\mathrm{CO}_{2}",
    "SO_{2}": r"\mathrm{SO}_{2}",
    "SO_{3}": r"\mathrm{SO}_{3}",
    "H_{2}O": r"\mathrm{H}_{2}\mathrm{O}",
}
CHEM_RE = re.compile("(?<![A-Za-z0-9])(" + "|".join(re.escape(k) for k in CHEM) + ")(?![A-Za-z0-9])")

# 线性符号 → LaTeX 命令（先做长的，避免 °C 被当成 °）
DEGREE_SCRIPT = [("^{°}", r"^{\circ}"), ("_{°}", r"_{\circ}")]

SYMBOLS = [
    ("°C", r"^{\circ}\mathrm{C}"),
    ("°F", r"^{\circ}\mathrm{F}"),
    ("°", r"^{\circ}"),
    ("′", "'"),
    ("″", "''"),
    ("×", r"\times "),
    ("−", "-"),
    ("·", r"\cdot "),
    ("÷", r"\div "),
    ("≈", r"\approx "),
    ("≠", r"\neq "),
    ("≤", r"\le "),
    ("≥", r"\ge "),
    ("∝", r"\propto "),
    ("±", r"\pm "),
    ("∞", r"\infty "),
    ("→", r"\to "),
    ("—", r"\text{---}"),
    ("～", r"\sim "),
    ("~", r"\sim "),
    ("√", r"\sqrt"),
    ("Σ", r"\sum "),
]

GREEK = {
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "ε": r"\varepsilon",
    "ζ": r"\zeta", "η": r"\eta", "θ": r"\theta", "ι": r"\iota", "κ": r"\kappa",
    "λ": r"\lambda", "μ": r"\mu", "ν": r"\nu", "ξ": r"\xi", "π": r"\pi",
    "ρ": r"\rho", "ς": r"\sigma", "σ": r"\sigma", "τ": r"\tau", "υ": r"\upsilon",
    "φ": r"\varphi", "χ": r"\chi", "ψ": r"\psi", "ω": r"\omega",
    "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda", "Ξ": r"\Xi",
    "Π": r"\Pi", "Υ": r"\Upsilon", "Φ": r"\Phi", "Ψ": r"\Psi", "Ω": r"\Omega",
}
GREEK_RE = re.compile("[" + "".join(GREEK) + "]")

FUNCS = ("ln", "lg", "log", "exp", "sin", "cos", "tan", "arctan", "arcsin", "arccos", "sinh", "cosh", "tanh")
FUNC_RE = re.compile(r"(?<![A-Za-z\\])(" + "|".join(FUNCS) + r")(?![A-Za-z])")

# sqrt(...) 也出现在数据里，和 √(...) 一样处理成 \sqrt{...}
SQRT_RE = re.compile(r"(?<![A-Za-z])sqrt\(")

# 单位：只在「数值后面」成组出现时才包成 \mathrm{}，避免把变量 u、x、R 当成单位
ATOM = (
    r"mmHg|kmol|kPa|MPa|atm|kJ|kW|MW|MJ|kcal|cal|min|Hz|mol|kg|mm|cm|dm|km|Pa|J|W|N|K|s|h|L|m|r"
)
PART = r"(?:°C|°F|" + ATOM + r")(?:\^\{[^{}]*\}|\^[0-9])?"
SEP = r"\s*(?:/|·|\*)\s*"
# 单位只认「数字或上一段结尾之后、到一个明确断点之前」的串，前后都夹住才敢包 \mathrm{}
# 前缀必须是数字或数字的幂（1.41 m、10^{-3}Pa·s），否则 q_{m1}r 里的 r 会被当成单位
UNIT_RE = re.compile(
    r"(?P<pre>[0-9]|\^\{[-\d.]+\}|\^\d)\s*(?P<unit>" + PART + r"(?:" + SEP + PART + r")*)"
    r"(?=\s*(?:$|[=,;、，。；：）(×<≥≤≈*]))"
    r"(?![A-Za-z0-9_^{])"
)

# 上下标里夹中文的（H_{g允}、Σh_{f吸入}），整组包进 \text{}，交给系统字体显示
CJK_SCRIPT = re.compile(r"([_^])\{([^{}]*[^\x00-\x7f][^{}]*)\}")
TEXT_GROUP = re.compile(r"\\text\{[^{}]*\}")

# 转换后仍允许出现的字符：LaTeX 语法本身 + ASCII（\text{} 里的中文除外）
SAFE = re.compile(r"^[\x00-\x7f]*$")
# 空白/标点命令后面紧跟上下标 = 没有基，KaTeX 会直接报错，宁可退回线性文本。
# 字母命令（\rho、\mathrm{m}）本身就是个原子，后面跟 ^、_ 是正常的，不能拦。
ORPHAN = re.compile(r"\\[,;:!](?=[ \t]*[\^_])")

_SENTINEL = re.compile(r"\x00(\d+)\x01")


def is_formula_line(line: str) -> bool:
    """整行都是公式：没有中日韩文字，且带等号或数学符号。"""
    s = line.strip()
    if not s or CJK.search(s):
        return False
    return bool(MATHY.search(s))


def _match_bracket(s: str, open_idx: int, opener: str, closer: str) -> int:
    """返回与 s[open_idx] 处的括号配对的闭括号下标，找不到返回 -1。"""
    depth = 0
    for i in range(open_idx, len(s)):
        if s[i] == opener:
            depth += 1
        elif s[i] == closer:
            depth -= 1
            if depth == 0:
                return i
    return -1


def _rewrite_sqrt(s: str) -> str:
    r"""把 √(...)、√[...]、sqrt(...) 统一成 \sqrt{...}，支持嵌套括号。"""
    s = SQRT_RE.sub(r"√(", s)
    out: list[str] = []
    i = 0
    while i < len(s):
        nxt = s[i + 1] if i + 1 < len(s) else ""
        if s[i] == "√" and nxt in "([":
            closer = ")" if nxt == "(" else "]"
            end = _match_bracket(s, i + 1, nxt, closer)
            if end > 0:
                out.append("\\sqrt{" + _rewrite_sqrt(s[i + 2 : end]) + "}")
                i = end + 1
                continue
        out.append(s[i])
        i += 1
    return "".join(out)


def _unit_tex(group: str) -> str:
    """把一个单位串拆成 \\mathrm{} 片段：m^{3}/s → \\mathrm{m}^{3}/\\mathrm{s}。"""
    parts = []
    for piece in re.split(SEP, group):
        if not piece:
            continue
        m = re.match(r"(°C|°F|°)?(" + ATOM + r")?(\^\{[^{}]*\}|\^[0-9])?", piece)
        if not m:
            return ""
        deg, body, pow_ = m.group(1) or "", m.group(2) or "", m.group(3) or ""
        if deg:
            parts.append(r"^{\circ}\mathrm{" + deg[1] + "}" + pow_)
        elif body:
            parts.append(r"\mathrm{" + body + "}" + pow_)
        else:
            return ""
    if not parts:
        return ""
    # 保留原来的分隔符
    seps = re.findall(SEP, group)
    joined = parts[0]
    for sep, part in zip(seps, parts[1:]):
        joined += ("/" if "/" in sep else r"\cdot ") + part
    return joined


def _protect_units(s: str, box: list[str]) -> str:
    """数值后的单位串先藏起来，免得被符号替换拆散。"""

    def repl(m: re.Match) -> str:
        tex = _unit_tex(m.group("unit"))
        if not tex:
            return m.group(0)
        # ^{\circ} 这类以脚本开头的，要垫一个空底，否则 KaTeX 报「上标没有基」
        box.append("\\," + ("{}" if tex[:1] in "^_" else "") + tex)
        return m.group("pre") + "\x00%d\x01" % (len(box) - 1)

    return UNIT_RE.sub(repl, s)


# 超过这个长度的公式单独占一行：手机上塞在中文叙述里会顶穿卡片，横向拖动很难读
LINE_MAX = 40
# 等号拆完还是太长（一长串加减项）时，继续按顶层加减号折行；手机上宁可多占几行也别横向拖动。
# 实测一个字符折合约 4.3px，手机正文一行的可用宽度 328px，即 76 字符上下才真正放不下；
# 但行内公式前面还夹着「（1）」这类编号占位，所以阈值取得比理论值紧一些
TERM_MAX = 58
FACTOR_MAX = 58
# 加减号前面是这些字符时它是「一元」的（如 = -5、×(-3)），不能当折行点
_UNARY_BEFORE = set("=(,+-·×/\\^_")


def split_chain(s: str) -> list[str]:
    """按顶层等号切分计算链，切点落在第二个及之后的等号上（等号留在下一行开头）。"""
    segs: list[str] = []
    buf: list[str] = []
    depth = 0
    seen = 0
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "=" and depth == 0 and seen and "".join(buf).strip():
            segs.append("".join(buf).strip())
            buf = [ch]
        else:
            if ch == "=" and depth == 0:
                seen += 1
            buf.append(ch)
    if "".join(buf).strip():
        segs.append("".join(buf).strip())
    return segs


def _split_binary(s: str, ops: str, limit: int) -> list[str]:
    """超过 limit 就在顶层的 ops 运算符前折行，运算符留到下一段开头。

    只认「二元」运算符：前面是数字、字母、括号或 } 收尾才算，
    于是 = -5、×(-3)、10^{-3} 这类一元的或括号内的都不会被当成折行点。
    """
    if len(s) <= limit:
        return [s]
    segs: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        prev = "".join(buf).rstrip()
        binary = (
            depth == 0
            and ch in ops
            and buf
            and bool(prev)
            and prev[-1] not in _UNARY_BEFORE
            and prev.strip("= ")
        )
        if binary:
            segs.append(prev)
            buf = [ch]
        else:
            buf.append(ch)
    if "".join(buf).strip():
        segs.append("".join(buf).strip())
    return segs if len(segs) > 1 else [s]


def split_terms(s: str) -> list[str]:
    """把过长的加减串按顶层 +、− 折行。"""
    return _split_binary(s, "+−-", TERM_MAX)


def split_factors(s: str) -> list[str]:
    """加减号拆完还长的，再按顶层 ×、· 折行（连乘链，如 0.725×[...]×...）。"""
    return _split_binary(s, "×·", FACTOR_MAX)


def to_tex(line: str) -> str | None:
    """把一行线性文本映射成 LaTeX；认不出就返回 None。"""
    s = line.strip()
    if not s or s[0] in "^_":
        return None
    # p^{°}_{A} 这种先把 ° 换成 \circ，否则下面会把 ^{°} 当成「带中文的下标」包进 \text{}
    s = CHEM_RE.sub(lambda m: CHEM[m.group(1)], s)
    for src, dst in DEGREE_SCRIPT:
        s = s.replace(src, dst)
    s = CJK_SCRIPT.sub(lambda m: m.group(1) + "{\\text{" + m.group(2) + "}}", s)
    box: list[str] = []
    s = _protect_units(s, box)
    s = _rewrite_sqrt(s)
    for src, dst in SYMBOLS:
        s = s.replace(src, dst)
    s = GREEK_RE.sub(lambda m: GREEK[m.group(0)] + " ", s)
    s = FUNC_RE.sub(lambda m: "\\" + m.group(1) + " ", s)
    # 裸下标（如 x_D）补上花括号，否则 KaTeX 只把下一个字符当下标
    s = re.sub(r"_(?!\{)([A-Za-z0-9])", r"_\1", s)
    s = re.sub(r"(?<!\^)\^(?!\{)([A-Za-z0-9])", r"^\1", s)
    s = _SENTINEL.sub(lambda m: box[int(m.group(1))], s)
    s = s.replace("%", r"\%")
    if not SAFE.match(TEXT_GROUP.sub("", s)) or ORPHAN.search(s):
        return None
    if s.count("{") != s.count("}") or s.count("(") != s.count(")") or s.count("[") != s.count("]"):
        return None
    return s


def _inline_runs(line: str) -> list[tuple[str, str, str]]:
    """混排行里切出「不含中文」的连续片段，逐段试着转 LaTeX。

    转不动的片段原样留在文本里，所以中文叙述不会被误伤。
    """
    out: list[tuple[str, str, str]] = []
    pos = 0
    for m in LATIN_RUN.finditer(line):
        if m.start() > pos:
            out.append(("text", line[pos : m.start()], ""))
        run = m.group(0)
        tex = to_tex(run) if MATHY.search(run) else None
        if tex:
            out.append(("math", tex, run.strip()))
        else:
            out.append(("text", run, ""))
        pos = m.end()
    if pos < len(line):
        out.append(("text", line[pos:], ""))
    return out


def convert_line(line: str) -> list[tuple[str, str, str]]:
    """一行 → [(kind, payload, fallback)]。

    kind 为 'text' 时 payload 就是原片段；为 'math' / 'math-block' 时
    payload 是 LaTeX，fallback 是给人看的线性原文（脚本不跑也能读）。
    """
    return _merge_text(_own_line(_segments(line)))


def _merge_text(segs: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """相邻的文本片段合并。

    切片段是按「有没有中文」下刀的，而 **加粗** 常常正好跨过中文（**气、液两相**），
    切开以后星号落在两段里，粗体就丢了。这里把中间的文本刀口再缝回去。
    """
    out: list[tuple[str, str, str]] = []
    for kind, payload, fallback in segs:
        if kind == "text" and out and out[-1][0] == "text":
            out[-1] = ("text", out[-1][1] + payload, "")
        else:
            out.append((kind, payload, fallback))
    return out


def _breaks(s: str) -> list[str]:
    """一条独立公式的折行点：先按等号，等号拆完还长的再按加减号。"""
    if len(s) <= LINE_MAX:
        return [s]
    out: list[str] = []
    for seg in split_chain(s):
        for piece in split_terms(seg):
            out.extend(split_factors(piece))
    return out


def _segments(line: str) -> list[tuple[str, str, str]]:
    if is_formula_line(line):
        stripped = line.strip()
        chain = _breaks(stripped)
        pieces = [to_tex(seg) for seg in chain]
        if len(chain) > 1 and all(pieces):
            return [("math-block", tex, seg) for seg, tex in zip(chain, pieces)]
        if pieces[0]:
            return [("math-block", pieces[0], stripped)]
        return [("text", line, "")]
    return _inline_runs(line)


def _promote(run: str) -> list[tuple[str, str, str]]:
    """行内的长公式：单独成行，等号链能拆就顺着等号拆行。"""
    chain = _breaks(run)
    pieces = [to_tex(seg) for seg in chain]
    if not all(pieces):
        tex = to_tex(run)
        return [("math-block", tex, run)] if tex else [("text", run, "")]
    return _pad([("math-block", tex, seg) for seg, tex in zip(chain, pieces)])


def _pad(blocks: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for b in blocks:
        if out:
            out.append(("break", "", ""))
        out.append(b)
    return out


def _own_line(segs: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """把过长的公式提成独立一行，并在它前后插入换行（kind == 'break'）。"""
    out: list[tuple[str, str, str]] = []
    for kind, payload, fallback in segs:
        if kind == "math" and len(fallback) > LINE_MAX:
            if out and out[-1][0] != "break":
                out.append(("break", "", ""))
            out.extend(_promote(fallback))
            continue
        if kind == "math-block" and out and out[-1][0] != "break":
            out.append(("break", "", ""))
        out.append((kind, payload, fallback))
        if kind == "math-block":
            out.append(("break", "", ""))
    while out and out[-1][0] == "break":
        out.pop()
    if out and out[0][0] == "break":
        out.pop(0)
    return out
