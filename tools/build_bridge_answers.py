"""桥接模式示例：演示 answers.json 的格式。

这里的 21 道题由当前会话的智能体（也就是"我"）依据导出的提示词逐块作答，
evidence 一律逐字取自 samples/过拟合与正则化.md，覆盖单选 / 多选 / 判断 /
填空 / 简答五种题型。真实使用时换成任何能读提示词的模型即可。

跑法：
    python run.py samples/过拟合与正则化.md --emit-prompts out/prompts.json -n 3
    python tools/build_bridge_answers.py          # 产出 out/answers.json
    python run.py samples/过拟合与正则化.md --answers out/answers.json -n 3
"""

from __future__ import annotations

import json
from pathlib import Path

Q: list[list[dict]] = [
    # ---------------------------------------------------------- chunk 1 · 3.1
    [
        {
            "type": "single",
            "bloom": "理解",
            "difficulty": "medium",
            "question": "判断一个模型是否发生过拟合，最可靠的外部信号是什么？",
            "options": [
                "A. 训练损失本身的绝对值偏大",
                "B. 训练损失与验证损失之间的差距持续扩大",
                "C. 验证损失在训练初期就高于随机水平",
                "D. 模型参数总量超过训练样本数",
            ],
            "answer": "B",
            "explanation": "原文明确否定了用训练损失绝对值来判断，真正的信号是两条损失曲线的差距是否在扩大。",
            "evidence": "判断过拟合的可靠信号不是训练损失的大小，而是训练损失与验证损失之间的差距是否在扩大。",
        },
        {
            "type": "truefalse",
            "bloom": "记忆",
            "difficulty": "easy",
            "question": "过拟合的本质是模型把训练样本中的噪声也当作规律学习了。",
            "answer": "true",
            "explanation": "与原文对过拟合本质的表述一致：模型把噪声当成了可泛化的规律。",
            "evidence": "其本质是模型把训练样本中的噪声也当成了规律来学习。",
        },
        {
            "type": "short",
            "bloom": "理解",
            "difficulty": "easy",
            "question": "欠拟合在训练损失与验证损失上分别表现为什么？",
            "answer": "模型容量不足，连训练集的基本结构都无法拟合，因此训练损失和验证损失同时偏高。",
            "explanation": "关键点是「同时偏高」，这把它与过拟合的「一降一升」区分开。",
            "evidence": "欠拟合是指模型容量不足，连训练集的基本结构都无法拟合，表现为训练损失和验证损失同时偏高。",
        },
    ],
    # ---------------------------------------------------------- chunk 2 · 3.2
    [
        {
            "type": "single",
            "bloom": "记忆",
            "difficulty": "easy",
            "question": "模型的泛化误差被分解为哪三项？",
            "options": [
                "A. 偏差、方差与不可约噪声",
                "B. 偏差、方差与学习率",
                "C. 方差、噪声与正则项",
                "D. 偏差、模型容量与噪声",
            ],
            "answer": "A",
            "explanation": "原文给出的三项分解为偏差、方差与不可约噪声，学习率与正则项是训练手段，不是误差成分。",
            "evidence": "模型的泛化误差可以分解为偏差、方差与不可约噪声三项。",
        },
        {
            "type": "multiple",
            "bloom": "理解",
            "difficulty": "medium",
            "question": "关于偏差与方差，下列说法正确的有哪些？",
            "options": [
                "A. 偏差衡量模型假设空间与真实规律之间的系统性偏离",
                "B. 方差衡量模型对训练集扰动的敏感程度",
                "C. 高偏差对应欠拟合",
                "D. 高方差对应过拟合",
                "E. 偏差与方差随模型容量增加同时下降",
            ],
            "answer": ["A", "B", "C", "D"],
            "explanation": "前四项均为原文表述；E 错在二者走向相反——容量增加时偏差下降而方差上升。",
            "evidence": "偏差衡量模型假设空间与真实规律之间的系统性偏离，方差衡量模型对训练集扰动的敏感程度。高偏差对应欠拟合，高方差对应过拟合。",
        },
        {
            "type": "fill",
            "bloom": "记忆",
            "difficulty": "medium",
            "question": "随着模型容量增加，偏差下降而方差上升，泛化误差呈＿＿＿＿曲线。",
            "answer": "先降后升的 U 形",
            "explanation": "正因为不是单调关系，选容量的目标才是找曲线最低点，而不是一味加大模型。",
            "evidence": "随着模型容量增加，偏差下降而方差上升，泛化误差呈先降后升的 U 形曲线。",
        },
    ],
    # ---------------------------------------------------------- chunk 3 · 3.3
    [
        {
            "type": "single",
            "bloom": "应用",
            "difficulty": "medium",
            "question": "把 L2 正则化的惩罚系数 λ 调得过大，会出现什么后果？",
            "options": [
                "A. 权重被压得过小，模型转为欠拟合",
                "B. 权重被精确压到零，产生稀疏解",
                "C. 正则化项消失，退化为普通最小二乘",
                "D. 模型对训练集噪声变得更敏感",
            ],
            "answer": "A",
            "explanation": "λ 的两端都会出问题：趋零则失去正则效果，过大则权重被压得过小、模型转为欠拟合。",
            "evidence": "当 λ 趋于零时，正则化项消失，模型退化为普通最小二乘；当 λ 过大时，权重被压得过小，模型转为欠拟合。",
        },
        {
            "type": "multiple",
            "bloom": "理解",
            "difficulty": "hard",
            "question": "关于惩罚系数 λ 的两种极端取值，下列说法正确的有哪些？",
            "options": [
                "A. λ 趋于零时正则化项消失，模型退化为普通最小二乘",
                "B. λ 过大时权重被压得过小，模型转为欠拟合",
                "C. λ 越大正则化约束越弱",
                "D. λ 等于零时模型仍保留权重衰减",
            ],
            "answer": ["A", "B"],
            "explanation": "C 把方向说反了；D 与原文相反——λ 为零时正则项消失，权重衰减也随之消失。",
            "evidence": "当 λ 趋于零时，正则化项消失，模型退化为普通最小二乘；当 λ 过大时，权重被压得过小，模型转为欠拟合。",
        },
        {
            "type": "truefalse",
            "bloom": "记忆",
            "difficulty": "easy",
            "question": "L2 正则化使权重整体收缩到接近零但不等于零，因此也被称为权重衰减。",
            "answer": "true",
            "explanation": "这正是「权重衰减」这一别名的来源；注意是接近零而非精确为零，后者是 L1 的特征。",
            "evidence": "其效果是使权重整体收缩到接近零但不等于零，因此也被称为权重衰减。",
        },
    ],
    # ---------------------------------------------------------- chunk 4 · 3.4
    [
        {
            "type": "single",
            "bloom": "分析",
            "difficulty": "medium",
            "question": "L1 正则化相对于 L2 的核心差别是什么？",
            "options": [
                "A. 倾向于把一部分权重精确地压到零，产生稀疏解",
                "B. 惩罚项是权重向量的平方和，收缩更平滑",
                "C. 不需要惩罚系数，因此无需调参",
                "D. 使所有权重整体均匀收缩但都不为零",
            ],
            "answer": "A",
            "explanation": "稀疏解是 L1 的判别性特征，也正因如此它常被当作特征选择的替代手段。",
            "evidence": "与 L2 不同，L1 倾向于把一部分权重精确地压到零，从而产生稀疏解，因此常被用作特征选择的替代手段。",
        },
        {
            "type": "multiple",
            "bloom": "分析",
            "difficulty": "hard",
            "question": "从几何角度看，L1 为什么容易产生稀疏解？下列表述正确的有哪些？",
            "options": [
                "A. L1 的约束区域是菱形",
                "B. 菱形的顶点落在坐标轴上",
                "C. 最优解更容易出现在顶点处，此时部分权重恰为零",
                "D. L1 的约束区域是圆形，各方向到原点距离相等",
                "E. 稀疏性与惩罚项的形状无关",
            ],
            "answer": ["A", "B", "C"],
            "explanation": "原文给出的三步推理是：菱形约束区 → 顶点在坐标轴上 → 最优解落在顶点则部分权重为零。D、E 与这一解释直接冲突。",
            "evidence": "稀疏性的几何解释是：L1 的约束区域是菱形，其顶点落在坐标轴上，最优解更容易出现在顶点处，此时部分权重恰为零。",
        },
        {
            "type": "fill",
            "bloom": "记忆",
            "difficulty": "easy",
            "question": "L1 正则化在损失函数中加入权重＿＿＿＿之和作为惩罚项。",
            "answer": "绝对值",
            "explanation": "对比记忆：L2 加的是平方和，L1 加的是绝对值之和。",
            "evidence": "L1 正则化在损失函数中加入权重绝对值之和作为惩罚项。",
        },
    ],
    # ---------------------------------------------------------- chunk 5 · 3.5
    [
        {
            "type": "single",
            "bloom": "应用",
            "difficulty": "medium",
            "question": "Dropout 在推理阶段需要做怎样的处理？",
            "options": [
                "A. 继续按概率 p 随机置零一部分神经元",
                "B. 不丢弃神经元，但把权重按保留概率缩放",
                "C. 把所有神经元的输出统一减半",
                "D. 完全不做任何调整",
            ],
            "answer": "B",
            "explanation": "训练时随机置零、推理时不置零但缩放权重，两者配合才能保持输出期望值一致。",
            "evidence": "推理阶段不丢弃任何神经元，但需要把权重按保留概率进行缩放，以保持输出的期望值一致。",
        },
        {
            "type": "truefalse",
            "bloom": "记忆",
            "difficulty": "easy",
            "question": "Dropout 的概率 p 常用取值范围是 0.2 到 0.5，p 过大会导致训练不收敛。",
            "answer": "true",
            "explanation": "与原文一致；这也是实践中不会把 p 设得很高的原因。",
            "evidence": "p 的常用取值范围是 0.2 到 0.5，p 过大会导致训练不收敛。",
        },
        {
            "type": "short",
            "bloom": "理解",
            "difficulty": "medium",
            "question": "为什么说 Dropout 具有降低方差的效果？",
            "answer": "可以把它理解为对大量共享权重的子网络做隐式集成，集成降低了方差。",
            "explanation": "关键在「隐式集成」这个视角：每次迭代丢弃不同神经元，相当于训练了不同的子网络并对它们做平均。",
            "evidence": "Dropout 可以理解为对大量共享权重的子网络做隐式集成，因此具有降低方差的效果。",
        },
    ],
    # ---------------------------------------------------------- chunk 6 · 3.6
    [
        {
            "type": "single",
            "bloom": "理解",
            "difficulty": "medium",
            "question": "早停被称作最廉价的正则化手段，它的代价是什么？",
            "options": [
                "A. 需要修改损失函数的结构",
                "B. 需要额外划出一部分数据作为验证集",
                "C. 必须额外引入一个惩罚系数",
                "D. 训练轮数被迫大幅增加",
            ],
            "answer": "B",
            "explanation": "早停不碰损失函数，唯一代价是要留出验证集来监控损失曲线。",
            "evidence": "它不需要修改损失函数，是最廉价的正则化手段，其代价是需要额外划出一部分数据作为验证集。",
        },
        {
            "type": "multiple",
            "bloom": "分析",
            "difficulty": "hard",
            "question": "关于数据增广的合法性，下列说法正确的有哪些？",
            "options": [
                "A. 取决于变换是否保持语义不变",
                "B. 对图像做水平翻转通常是合法的",
                "C. 对医学影像做翻转可能改变诊断含义，因而不一定合法",
                "D. 任何几何变换都是合法增广",
            ],
            "answer": ["A", "B", "C"],
            "explanation": "原文用「图像翻转通常合法、医学影像翻转可能改变诊断含义」这一对照说明：合法性由是否保持语义不变决定，D 的说法过于绝对。",
            "evidence": "增广的合法性取决于变换是否保持语义不变：对图像做水平翻转通常合法，对医学影像做翻转则可能改变诊断含义。",
        },
        {
            "type": "fill",
            "bloom": "记忆",
            "difficulty": "medium",
            "question": "早停是指验证损失连续若干轮不再下降时终止训练，并回滚到＿＿＿＿的那一轮参数。",
            "answer": "验证损失最低",
            "explanation": "回滚目标是最低点而不是停止点，这一点容易在实现时写错。",
            "evidence": "早停是指在验证损失连续若干轮不再下降时终止训练，并回滚到验证损失最低的那一轮参数。",
        },
    ],
    # ---------------------------------------------------------- chunk 7 · 3.7
    [
        {
            "type": "single",
            "bloom": "分析",
            "difficulty": "medium",
            "question": "按本章的三分法，Dropout 属于哪一类抑制过拟合的手段？",
            "options": [
                "A. 约束模型复杂度",
                "B. 约束训练过程",
                "C. 扩大有效数据",
                "D. 降低模型容量",
            ],
            "answer": "B",
            "explanation": "三类分别是：约束复杂度（L1/L2）、约束训练过程（早停/Dropout）、扩大有效数据（数据增广）。",
            "evidence": "抑制过拟合的手段分为三类：约束模型复杂度（L1、L2）、约束训练过程（早停、Dropout）、扩大有效数据（数据增广）。",
        },
        {
            "type": "truefalse",
            "bloom": "理解",
            "difficulty": "medium",
            "question": "判别一个模型是否过拟合，应当依赖训练损失的绝对数值，而不是训练损失与验证损失之间的差距。",
            "answer": "false",
            "explanation": "原文的说法正好相反：判别依据是两者差距，而非训练损失的绝对值。",
            "evidence": "过拟合的判别依赖训练损失与验证损失的差距，而非训练损失的绝对值。",
        },
        {
            "type": "short",
            "bloom": "应用",
            "difficulty": "hard",
            "question": "在多种抑制过拟合的手段之间做选择时，原文认为应当依据什么？",
            "answer": "取决于数据规模与算力预算，通常需要组合使用，而不是只挑一种。",
            "explanation": "这条结论把前面所有手段串了起来：不是找唯一最优解，而是按资源约束做组合。",
            "evidence": "选择哪一种取决于数据规模与算力预算，通常需要组合使用。",
        },
    ],
]


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "out" / "answers.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"answers": [{"text": json.dumps(chunk, ensure_ascii=False)} for chunk in Q]}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(c) for c in Q)
    print(f"已写出 {out} · {len(Q)} 块 · {total} 题")


if __name__ == "__main__":
    main()
