"""生成模式（预设高级参数）。

三档模式映射为一组高级参数，由服务层并入 generate 调用：
  - 快速：更低步数/引导值，换更快出图
  - 标准：不覆盖任何参数，完全用厂商默认
  - 创造：更高的步数与引导值，细节与提示词遵循度更好

说明：仅硅基流动（及部分 OpenAI 风格厂商）支持 steps/guidance 类参数；
不支持的客户端会自动忽略这些参数，因此无需按厂商特殊处理。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class GenerationMode:
    """一个生成模式档位。"""

    id: str          # fast / standard / creative
    name: str        # 界面显示名
    description: str
    # 覆盖的高级参数（None = 不发送，用厂商默认）
    num_inference_steps: Optional[int] = None
    guidance_scale: Optional[float] = None


GENERATION_MODES = [
    GenerationMode(
        id="fast",
        name="快速",
        description="更低步数与引导值，优先出图速度",
        num_inference_steps=16,
        guidance_scale=4.5,
    ),
    GenerationMode(
        id="standard",
        name="标准",
        description="使用模型默认参数（推荐）",
    ),
    GenerationMode(
        id="creative",
        name="创造",
        description="更高步数与引导值，细节与遵循度更好，耗时更长",
        num_inference_steps=40,
        guidance_scale=7.5,
    ),
]

_DEFAULT = "standard"


def get_mode(mode_id: str | None) -> GenerationMode:
    """按 ID 取模式，未知值回退到标准。"""
    for m in GENERATION_MODES:
        if m.id == mode_id:
            return m
    return GENERATION_MODES[1]


def mode_kwargs(mode_id: str | None) -> dict:
    """把模式转成可并入 generate() 的高级参数字典。

    标准模式返回空字典（所有参数保持 None，即厂商默认）。
    """
    m = get_mode(mode_id)
    kwargs: dict = {}
    if m.num_inference_steps is not None:
        kwargs["num_inference_steps"] = m.num_inference_steps
    if m.guidance_scale is not None:
        kwargs["guidance_scale"] = m.guidance_scale
    return kwargs
