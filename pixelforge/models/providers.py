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
    doc_url: str = ""             # 获取 API Key 的控制台页面


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


# ----------------------------------------------------------------------
# 智谱 BigModel（CogView 系列）
# 同步 OpenAI 风格 /images/generations，响应 data[].url。
# 无 /models 查询接口，模型为固定枚举，直接用静态表。
# ----------------------------------------------------------------------
ZHIPU_IMAGE_MODEL_CANDIDATES: List[str] = [
    "cogview-4",
    "cogview-3-flash",
    "glm-image",
]

ZHIPU_IMAGE_DISPLAY_NAMES: Dict[str, str] = {
    "cogview-4": "CogView-4",
    "cogview-3-flash": "CogView-3-Flash (免费)",
    "glm-image": "GLM-Image",
}

ZHIPU_IMAGE_SIZES: Dict[str, List[str]] = {
    # cogview 系列：512–2048px，16 的倍数
    "cogview-4": ["1024x1024", "768x1344", "864x1152", "1344x768", "1152x864", "1440x720", "720x1440"],
    "cogview-3-flash": ["1024x1024", "768x1344", "864x1152", "1344x768", "1152x864", "1440x720", "720x1440"],
    # glm-image：推荐尺寸，32 的倍数，仅 hd
    "glm-image": ["1280x1280", "1568x1056", "1056x1568", "1472x1088", "1088x1472", "1728x960", "960x1728"],
}


# ----------------------------------------------------------------------
# 火山方舟 Volcano Ark（Doubao Seedream 系列）
# OpenAI 风格同步 /images/generations，响应 data[].url。
# Seedream 4.x 同一模型支持文生图与参考图输入（图生图）。
# 注意：调用前需在方舟控制台开通对应模型服务。
# ----------------------------------------------------------------------
ARK_IMAGE_MODEL_CANDIDATES: List[str] = [
    "doubao-seedream-4-0-250828",
    "doubao-seedream-4-5-251128",
]

ARK_IMAGE_DISPLAY_NAMES: Dict[str, str] = {
    "doubao-seedream-4-0-250828": "Seedream 4.0",
    "doubao-seedream-4-5-251128": "Seedream 4.5",
}

ARK_IMAGE_SIZES: Dict[str, List[str]] = {
    # Seedream 4.0：1K~4K 均可，实测最低支持 1024x1024
    "doubao-seedream-4-0-250828": ["2048x2048", "1024x1024", "2304x1728", "1728x2304", "2K", "4K"],
    # Seedream 4.5：实测要求总像素 >= 3686400，1024x1024 会被拒绝
    "doubao-seedream-4-5-251128": ["2048x2048", "2304x1728", "1728x2304", "2K", "4K"],
}

# ----------------------------------------------------------------------
# MiniMax（image-01 系列）
# 自有接口 POST /v1/image_generation，响应 data.image_urls[]。
# 同一端点支持文生图；图生图走 subject_reference（人物主体参考）。
# ----------------------------------------------------------------------
MINIMAX_IMAGE_MODEL_CANDIDATES: List[str] = [
    "image-01",
    "image-01-live",
]

MINIMAX_IMAGE_DISPLAY_NAMES: Dict[str, str] = {
    "image-01": "MiniMax image-01",
    "image-01-live": "MiniMax image-01-live",
}

MINIMAX_IMAGE_SIZES: Dict[str, List[str]] = {
    # width/height：512–2048px，8 的倍数
    "image-01": ["1024x1024", "1024x576", "1360x768", "768x1360", "576x1024", "2048x2048"],
    "image-01-live": ["1024x1024", "1024x576", "1360x768", "768x1360", "576x1024"],
}


# ----------------------------------------------------------------------
# 腾讯混元 Hy-Image（TokenHub / tencentmaas 新平台）
# 同步 OpenAI 风格接口（官方示例端点，响应 data[].url）。
# 已实测：size 限制为面积 <= 1024x1024（1280x720 等非方形可用，
# 2048x2048 报"图片面积不能超过1024x1024"）；image 字段传 data URL
# 即为图生图。Bearer 鉴权用控制台的 sk- API Key（非 SecretId/Key）。
# ----------------------------------------------------------------------
HUNYUAN_IMAGE_MODEL_CANDIDATES: List[str] = [
    "hy-image-v3",
]

HUNYUAN_IMAGE_DISPLAY_NAMES: Dict[str, str] = {
    "hy-image-v3": "混元 Hy-Image 3.0",
}

HUNYUAN_IMAGE_SIZES: Dict[str, List[str]] = {
    # 面积上限 1024x1024，均为已验证或同面积档位
    "hy-image-v3": ["1024x1024", "1280x720", "720x1280", "1024x576", "576x1024", "960x960"],
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
    doc_url="https://cloud.siliconflow.cn/account/ak",
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
    doc_url="https://bailian.console.aliyun.com/?apiKey=1",
    models=make_models(QIANWEN_IMAGE_MODEL_CANDIDATES),
)


# 智谱 BigModel：api_base 不含尾部的 /images/generations
ZHIPU = Provider(
    id="zhipu",
    name="智谱 (BigModel)",
    api_base="https://open.bigmodel.cn/api/paas/v4",
    api_key_env="ZHIPU_API_KEY",
    doc_url="https://open.bigmodel.cn/usercenter/apikeys",
    models=make_models(ZHIPU_IMAGE_MODEL_CANDIDATES),
)


# 火山方舟：需在方舟控制台开通模型服务后才可调用
ARK = Provider(
    id="ark",
    name="火山方舟 (Volcano Ark)",
    api_base="https://ark.cn-beijing.volces.com/api/v3",
    api_key_env="ARK_API_KEY",
    doc_url="https://console.volcengine.com/ark/region:ark-cn-beijing/apiKey",
    models=make_models(ARK_IMAGE_MODEL_CANDIDATES),
)

MINIMAX = Provider(
    id="minimax",
    name="MiniMax",
    api_base="https://api.minimaxi.com/v1",
    api_key_env="MINIMAX_API_KEY",
    doc_url="https://platform.minimaxi.com/user-center/basic-information/interface-key",
    models=make_models(MINIMAX_IMAGE_MODEL_CANDIDATES),
)


# 腾讯混元：TokenHub 新平台，Bearer 用 sk- API Key
HUNYUAN = Provider(
    id="hunyuan",
    name="腾讯混元 (Hy-Image)",
    api_base="https://tokenhub.tencentmaas.com/v1",
    api_key_env="HUNYUAN_API_KEY",
    doc_url="https://tokenhub.tencentmaas.com",
    models=make_models(HUNYUAN_IMAGE_MODEL_CANDIDATES),
)


# 自定义厂商：OpenAI 协议，base URL 与模型 ID 由用户在设置中填写
CUSTOM = Provider(
    id="custom",
    name="自定义 (OpenAI 协议)",
    api_base="",
    api_key_env="CUSTOM_API_KEY",
    models=[],  # 动态来自设置中用户填写的模型 ID
)


# 后续扩展时在此追加新厂商适配器
PROVIDERS: List[Provider] = [
    SILICONFLOW, QIANWEN, ZHIPU, ARK, MINIMAX, HUNYUAN, CUSTOM,
]


def get_provider(provider_id: str) -> Optional[Provider]:
    """按 ID 查找厂商。"""
    for p in PROVIDERS:
        if p.id == provider_id:
            return p
    return None
