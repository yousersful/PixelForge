"""提示词模板。

为不熟悉提示词书写的用户提供预设模板，点击后填入提示词编辑框。
模板中可包含 {占位符}，选择模板时会自动替换为输入框中的描述（若为空则用提示）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class PromptTemplate:
    """一个提示词模板。"""

    name: str          # 模板名称（显示在下拉框中）
    category: str      # 分类：人像 / 风景 / 产品 / 插画 / 摄影 等
    text: str          # 模板文本，可含 {placeholder}
    placeholder: str = ""  # 占位符默认内容（替换 {占位符} 时使用）


# ----------------------------------------------------------------------
# 内置模板
# ----------------------------------------------------------------------
TEMPLATES: List[PromptTemplate] = [
    PromptTemplate(
        "写实人像", "人像",
        "{人物}的写实人像，柔和自然光，浅景深，细腻皮肤质感，专业摄影，8k",
        "面带微笑的年轻女性",
    ),
    PromptTemplate(
        "户外人像", "人像",
        "{人物}在户外阳光下的全身照，背景虚化，暖色调，胶片质感，时尚摄影",
        "穿着风衣的男人",
    ),
    PromptTemplate(
        "风景大片", "风景",
        "壮丽的{地点}，黄金时刻光线，层次丰富，广角构图，高清细节，风光摄影",
        "雪山湖泊",
    ),
    PromptTemplate(
        "城市夜景", "风景",
        "{城市}的城市夜景，霓虹灯光，长曝光，车流光轨，电影感，超高细节",
        "上海外滩",
    ),
    PromptTemplate(
        "产品展示", "产品",
        "{产品}的商业产品摄影，纯白背景，柔和棚拍灯光，材质细节清晰，电商主图",
        "高端蓝牙耳机",
    ),
    PromptTemplate(
        "电子产品", "产品",
        "{产品}的特写摄影，金属质感，浅景深，科技感打光，干净背景",
        "机械键盘",
    ),
    PromptTemplate(
        "动漫插画", "插画",
        "{内容}的动漫插画，鲜艳配色，干净线条，吉卜力风格，高完成度",
        "森林中的小精灵",
    ),
    PromptTemplate(
        "像素艺术", "插画",
        "{内容}的像素风游戏艺术，16位风格，复古配色，细节丰富",
        "中世纪村庄",
    ),
    PromptTemplate(
        "街拍人文", "摄影",
        "{场景}的街头摄影，纪实风格，富士胶片色彩，颗粒感，抓拍瞬间",
        "雨天打伞的路人",
    ),
    PromptTemplate(
        "宠物摄影", "摄影",
        "{宠物}的宠物摄影，暖色调，浅景深，可爱活泼，高清毛发细节",
        "金毛幼犬",
    ),
]


def get_templates(category: str | None = None) -> List[PromptTemplate]:
    """按分类获取模板；分类为空则返回全部。"""
    if not category:
        return TEMPLATES
    return [t for t in TEMPLATES if t.category == category]
