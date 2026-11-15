"""桥接模式示例：演示 answers.json 的格式。

这里的 14 道题由当前会话的智能体（也就是"我"）依据 out/prompts.json
逐块作答生成，evidence 一律逐字取自原文。
真实使用时，你换成任何能读提示词的模型/自动化流程即可。

跑法：
    python run.py samples/过拟合与正则化.md --emit-prompts out/prompts.json -n 2
    python tools/build_bridge_answers.py          # 产出 out/answers.json
    python run.py samples/过拟合与正则化.md --answers out/answers.json -n 2
"""

from __future__ import annotations

import json
from pathlib import Path

Q: list[list[dict]] = [
    # chunk 1 · 3.1 过拟合的定义
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
            "explanation": "原文明确指出，可靠信号是两条损失曲线的差距是否扩大，而不是训练损失的绝对大小。",
            "evidence": "判断过拟合的可靠信号不是训练损失的大小，而是训练损失与验证损失之间的差距是否在扩大。",
        },
        {
            "type": "truefalse",
            "bloom": "记忆",
            "difficulty": "easy",
            "question": "过拟合的本质是模型把训练样本中的噪声也当作规律学习了。",
            "answer": "true",
            "explanation": "这与原文对过拟合本质的表述一致。",
            "evidence": "其本质是模型把训练样本中的噪声也当成了规律来学习。",
        },
    ],
    # chunk 2 · 3.2 偏差与方差的权衡
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
            "explanation": "原文给出的三项分解为偏差、方差与不可约噪声。",
            "evidence": "模型的泛化误差可以分解为偏差、方差与不可约噪声三项。",
        },
        {
            "type": "single",
            "bloom": "理解",
            "difficulty": "medium",
            "question": "随着模型容量增加，泛化误差通常呈现什么变化？",
            "options": [
                "A. 单调下降",
                "B. 单调上升",
                "C. 先降后升的 U 形曲线",
                "D. 基本保持不变",
            ],
            "answer": "C",
            "explanation": "容量增加使偏差下降、方差上升，两者叠加形成 U 形曲线，因此目标是取最低点。",
            "evidence": "随着模型容量增加，偏差下降而方差上升，泛化误差呈先降后升的 U 形曲线。",
        },
    ],
    # chunk 3 · 3.3 L2 正则化
    [
        {
            "type": "single",
            "bloom": "记忆",
            "difficulty": "easy",
            "question": "L2 正则化常被称为什么？",
            "options": ["A. 权重衰减", "B. 特征选择", "C. 早停", "D. 稀疏编码"],
            "answer": "A",
            "explanation": "L2 使权重整体收缩到接近零但不为零，因此得名权重衰减。",
            "evidence": "其效果是使权重整体收缩到接近零但不等于零，因此也被称为权重衰减。",
        },
        {
            "type": "truefalse",
            "bloom": "理解",
            "difficulty": "medium",
            "question": "当惩罚系数 λ 过大时，L2 正则化会使模型转为欠拟合。",
            "answer": "true",
            "explanation": "λ 过大会把权重压得过小，导致模型容量不足。",
            "evidence": "当 λ 过大时，权重被压得过小，模型转为欠拟合。",
        },
    ],
    # chunk 4 · 3.4 L1 正则化与稀疏性
    [
        {
            "type": "single",
            "bloom": "理解",
            "difficulty": "medium",
            "question": "与 L2 相比，L1 正则化最本质的区别是什么？",
            "options": [
                "A. 能把一部分权重精确压到零，产生稀疏解",
                "B. 能让所有权重整体收缩但不为零",
                "C. 不需要设定惩罚系数",
                "D. 只能用于线性模型",
            ],
            "answer": "A",
            "explanation": "稀疏解使 L1 可替代特征选择，这是它区别于 L2 的关键。",
            "evidence": "与 L2 不同，L1 倾向于把一部分权重精确地压到零，从而产生稀疏解，因此常被用作特征选择的替代手段。",
        },
        {
            "type": "single",
            "bloom": "应用",
            "difficulty": "hard",
            "question": "从几何角度看，L1 的约束区域是什么形状，从而使最优解容易落在坐标轴上？",
            "options": ["A. 圆形", "B. 菱形", "C. 正方形", "D. 椭球"],
            "answer": "B",
            "explanation": "菱形顶点落于坐标轴，最优解落在顶点时部分权重恰为零。",
            "evidence": "稀疏性的几何解释是：L1 的约束区域是菱形，其顶点落在坐标轴上，最优解更容易出现在顶点处，此时部分权重恰为零。",
        },
    ],
    # chunk 5 · 3.5 Dropout
    [
        {
            "type": "single",
            "bloom": "理解",
            "difficulty": "medium",
            "question": "推理阶段使用 Dropout 训练的模型时，为什么要把权重按保留概率缩放？",
            "options": [
                "A. 提升推理速度",
                "B. 保持输出的期望值与训练时一致",
                "C. 进一步抑制过拟合",
                "D. 防止梯度爆炸",
            ],
            "answer": "B",
            "explanation": "训练时随机置零会改变输出期望，推理时必须按保留概率补偿。",
            "evidence": "推理阶段不丢弃任何神经元，但需要把权重按保留概率进行缩放，以保持输出的期望值一致。",
        },
        {
            "type": "single",
            "bloom": "记忆",
            "difficulty": "easy",
            "question": "Dropout 的丢弃概率 p 取多大合适？其取值过大有什么后果？",
            "options": [
                "A. 0.2 到 0.5；过大会导致训练不收敛",
                "B. 0.5 到 0.9；过大会导致欠拟合",
                "C. 0.01 到 0.1；过大会导致梯度消失",
                "D. 越接近 1 越好；无负面影响",
            ],
            "answer": "A",
            "explanation": "原文给出常用范围 0.2–0.5，并指出 p 过大会使训练不收敛。",
            "evidence": "p 的常用取值范围是 0.2 到 0.5，p 过大会导致训练不收敛。",
        },
    ],
    # chunk 6 · 3.6 早停与数据增广
    [
        {
            "type": "single",
            "bloom": "理解",
            "difficulty": "medium",
            "question": "早停作为正则化手段，其主要代价是什么？",
            "options": [
                "A. 必须修改损失函数",
                "B. 需要额外划出一部分数据作为验证集",
                "C. 显著增加训练算力",
                "D. 必须冻结部分网络层",
            ],
            "answer": "B",
            "explanation": "早停不改变损失函数，代价是要留出验证集来判断何时停止。",
            "evidence": "它不需要修改损失函数，是最廉价的正则化手段，其代价是需要额外划出一部分数据作为验证集。",
        },
        {
            "type": "truefalse",
            "bloom": "应用",
            "difficulty": "hard",
            "question": "对医学影像做水平翻转，属于合法的数据增广。",
            "answer": "false",
            "explanation": "翻转可能改变影像的解剖含义，因此不满足「保持语义不变」这一前提。",
            "evidence": "对图像做水平翻转通常合法，对医学影像做翻转则可能改变诊断含义。",
        },
    ],
    # chunk 7 · 3.7 本章小结
    [
        {
            "type": "single",
            "bloom": "记忆",
            "difficulty": "easy",
            "question": "本章把抑制过拟合的手段归纳为哪三类？",
            "options": [
                "A. 约束模型复杂度、约束训练过程、扩大有效数据",
                "B. 增大模型容量、延长训练时间、增加数据维度",
                "C. 提高学习率、减少层数、去除正则项",
                "D. 交叉验证、网格搜索、集成学习",
            ],
            "answer": "A",
            "explanation": "三类分别对应 L1/L2、早停与 Dropout、数据增广。",
            "evidence": "抑制过拟合的手段分为三类：约束模型复杂度（L1、L2）、约束训练过程（早停、Dropout）、扩大有效数据（数据增广）。",
        },
        {
            "type": "truefalse",
            "bloom": "理解",
            "difficulty": "easy",
            "question": "判断是否过拟合，主要看训练损失本身的绝对值。",
            "answer": "false",
            "explanation": "原文强调应看训练损失与验证损失的差距，而非绝对值。",
            "evidence": "过拟合的判别依赖训练损失与验证损失的差距，而非训练损失的绝对值。",
        },
    ],
]


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "out" / "answers.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"answers": [json.dumps({"questions": qs}, ensure_ascii=False) for qs in Q]}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写出 {out}（{len(Q)} 块 / {sum(len(x) for x in Q)} 题）")


if __name__ == "__main__":
    main()
