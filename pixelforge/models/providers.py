"""厂商与模型定义。

第一阶段接入硅基流动（SiliconFlow），采用 OpenAI 兼容格式。
每个厂商通过一个适配器对接，后续可扩展其他平台。

模型可用性说明：
  不同账户对不同模型的权限可能不同（如 FLUX 系列可能被禁用），
  因此不依赖硬编码的"可用列表"，而是运行时通过 /models 接口动态识别。
  IMAGE_MODEL_CANDIDATES 只是候选白名单，用于过滤出图像生成模型。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ModelInfo:
    """单个可用模型的描述。"""

    id: str            # 模型 ID，如 "Kwai-Kolors/Kolors"
    name: str          # 展示名称
    sizes: List[str] = field(default_factory=list)  # 支持的尺寸
    description: str = ""


@dataclass
class Provider:
    """一个 API 服务商的接入信息。"""

    id: str
    name: str
    api_base: str                 # API 端点
    api_key_env: str              # 环境变量名（可选）
    models: List[ModelInfo] = field(default_factory=list)


# ----------------------------------------------------------------------
# 图像模型候选白名单
# （/models 返回的模型包含大量 LLM，用此名单过滤出图像生成模型）
# ----------------------------------------------------------------------
IMAGE_MODEL_CANDIDATES: List[str] = [
    "Kwai-Kolors/Kolors",
    "Tongyi-MAI/Z-Image-Turbo",
    "Tongyi-MAI/Z-Image",
    "Qwen/Qwen-Image",
    "baidu/ERNIE-Image-Turbo",
    "black-forest-labs/FLUX.1-dev",
    "black-forest-labs/FLUX.1-schnell",
]

MODEL_DISPLAY_NAMES: Dict[str, str] = {
    "Kwai-Kolors/Kolors": "Kwai-Kolors 可图",
    "Tongyi-MAI/Z-Image-Turbo": "Z-Image Turbo 极速版",
    "Tongyi-MAI/Z-Image": "Z-Image",
    "Qwen/Qwen-Image": "Qwen-Image 通义万相",
    "baidu/ERNIE-Image-Turbo": "ERNIE-Image Turbo",
    "black-forest-labs/FLUX.1-dev": "FLUX.1-dev 高质量",
    "black-forest-labs/FLUX.1-schnell": "FLUX.1-schnell 极速",
}

# 各模型推荐尺寸（/models 不返回尺寸信息，此处提供通用候选）
MODEL_SIZES: Dict[str, List[str]] = {
    "Kwai-Kolors/Kolors": [
        "512x512", "768x768", "1024x1024",
        "1152x896", "1216x832", "1344x768",
    ],
    "Tongyi-MAI/Z-Image-Turbo": ["512x512", "768x768", "1024x1024"],
    "Tongyi-MAI/Z-Image": ["512x512", "768x768", "1024x1024"],
    "Qwen/Qwen-Image": ["512x512", "768x768", "1024x1024"],
    "baidu/ERNIE-Image-Turbo": ["512x512", "768x768", "1024x1024"],
    "black-forest-labs/FLUX.1-dev": ["512x512", "768x768", "1024x1024"],
    "black-forest-labs/FLUX.1-schnell": ["512x512", "768x768", "1024x1024"],
}

# ----------------------------------------------------------------------
# 图生图（图像编辑）模型候选
# ----------------------------------------------------------------------
IMAGE_EDIT_MODEL_CANDIDATES: List[str] = [
    "Qwen/Qwen-Image-Edit-2509",
    "Qwen/Qwen-Image-Edit",
]

IMAGE_EDIT_DISPLAY_NAMES: Dict[str, str] = {
    "Qwen/Qwen-Image-Edit-2509": "Qwen-Image-Edit (2509)",
    "Qwen/Qwen-Image-Edit": "Qwen-Image-Edit",
}

IMAGE_EDIT_SIZES: Dict[str, List[str]] = {
    "Qwen/Qwen-Image-Edit-2509": ["512x512", "768x768", "1024x1024"],
    "Qwen/Qwen-Image-Edit": ["512x512", "768x768", "1024x1024"],
}

# ----------------------------------------------------------------------
# 提示词优化所用的轻量文本 LLM（仅硅基流动，成本极低）
# ----------------------------------------------------------------------
PROMPT_OPTIMIZER_MODEL: str = "Qwen/Qwen3.5-9B"

# ----------------------------------------------------------------------
# 千问/百炼（DashScope 工作区）图片模型候选
# 原生异步 API，请求体用 input.messages（OpenAI 风格）。
# 已实测：wan2.7 系列可生成；qwen-image 系列在当前端点调用受限。
# ----------------------------------------------------------------------
QIANWEN_IMAGE_MODEL_CANDIDATES: List[str] = [
    "wan2.7-image-pro",
    "wan2.7-image",
]

QIANWEN_IMAGE_DISPLAY_NAMES: Dict[str, str] = {
    "wan2.7-image-pro": "万相 wan2.7-pro",
    "wan2.7-image": "万相 wan2.7",
    "z-image-turbo": "Z-Image Turbo",
}

QIANWEN_IMAGE_SIZES: Dict[str, List[str]] = {
    "wan2.7-image-pro": ["1024x1024", "1024x768", "768x1024", "2K"],
    "wan2.7-image": ["1024x1024", "1024x768", "768x1024", "2K"],
    "z-image-turbo": ["1024x1024"],
}

QIANWEN_IMAGE_EDIT_MODEL_CANDIDATES: List[str] = []

QIANWEN_IMAGE_EDIT_DISPLAY_NAMES: Dict[str, str] = {
    "qwen-image-edit-max": "千问图像编辑 max",
    "qwen-image-edit-plus": "千问图像编辑 plus",
}

QIANWEN_IMAGE_EDIT_SIZES: Dict[str, List[str]] = {
    "qwen-image-edit-max": ["1024x1024"],
    "qwen-image-edit-plus": ["1024x1024"],
}


def make_model(model_id: str) -> ModelInfo:
    """根据候选表创建一个 ModelInfo。"""
    return ModelInfo(
        id=model_id,
        name=MODEL_DISPLAY_NAMES.get(model_id, model_id),
        sizes=MODEL_SIZES.get(model_id, ["1024x1024"]),
    )


def make_models(model_ids: List[str]) -> List[ModelInfo]:
    """根据 ID 列表批量创建 ModelInfo。"""
    return [make_model(mid) for mid in model_ids]


# ----------------------------------------------------------------------
# 内置厂商定义
# ----------------------------------------------------------------------
SILICONFLOW = Provider(
    id="siliconflow",
    name="硅基流动 (SiliconFlow)",
    api_base="https://api.siliconflow.cn/v1",
    api_key_env="SILICONFLOW_API_KEY",
    # 无网络时的回退列表，仅含通常可用的模型
    models=make_models(
        [
            "Kwai-Kolors/Kolors",
            "Tongyi-MAI/Z-Image-Turbo",
            "Qwen/Qwen-Image",
        ]
    ),
)

# 千问/百炼工作区：实际 base 由用户在设置中填写（工作区专属 URL）
QIANWEN = Provider(
    id="qianwen",
    name="千问 / 百炼 (Qwen)",
    api_base="",
    api_key_env="DASHSCOPE_API_KEY",
    models=make_models(QIANWEN_IMAGE_MODEL_CANDIDATES),
)


# 后续扩展时在此追加新厂商适配器
PROVIDERS: List[Provider] = [SILICONFLOW, QIANWEN]


def get_provider(provider_id: str) -> Optional[Provider]:
    """按 ID 查找厂商。"""
    for p in PROVIDERS:
        if p.id == provider_id:
            return p
    return None
