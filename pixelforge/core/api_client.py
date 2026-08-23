"""SiliconFlow（硅基流动）API 客户端。

对接硅基流动的 OpenAI 兼容图像生成接口。

接口行为说明（已实测）：
  POST /images/generations 目前是**同步**返回结果，响应格式：
  {
    "images": [{"url": "https://..."}],
    "seed": 123,
    "timings": {...},
    "shared_id": "...",
    "created": 1787325410
  }

  为兼容未来可能改为异步任务接口的模型，本实现：
    1) 优先解析同步返回的 images；
    2) 若响应不含 images 但含 task id，则回退到 /tasks/{id} 轮询。
"""
from __future__ import annotations

import base64
import time
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

import requests

from pixelforge.models.providers import (
    IMAGE_EDIT_DISPLAY_NAMES,
    IMAGE_EDIT_MODEL_CANDIDATES,
    IMAGE_EDIT_SIZES,
    IMAGE_MODEL_CANDIDATES,
    MODEL_DISPLAY_NAMES,
    MODEL_SIZES,
    PROMPT_OPTIMIZER_MODEL,
    QIANWEN_IMAGE_DISPLAY_NAMES,
    QIANWEN_IMAGE_EDIT_DISPLAY_NAMES,
    QIANWEN_IMAGE_EDIT_MODEL_CANDIDATES,
    QIANWEN_IMAGE_EDIT_SIZES,
    QIANWEN_IMAGE_MODEL_CANDIDATES,
    QIANWEN_IMAGE_SIZES,
    ModelInfo,
    Provider,
)


class ApiError(Exception):
    """API 调用异常。"""


@dataclass
class GenerationResult:
    """一次生成的结果。"""

    images: List[bytes] = field(default_factory=list)  # 图片二进制数据
    seed: Optional[int] = None
    prompt: str = ""


class SiliconFlowClient:
    """硅基流动图像生成客户端。"""

    def __init__(self, provider: Provider, api_key: str) -> None:
        if not api_key:
            raise ApiError("缺少 API Key，请在设置中填写")
        self.provider = provider
        self.api_key = api_key
        self.base = provider.api_base
        self.timeout = 90

    # ------------------------------------------------------------------
    # 可用模型查询
    # ------------------------------------------------------------------
    def list_image_models(self) -> List[ModelInfo]:
        """查询当前账户可用的文生图模型。"""
        return self._list_models(
            IMAGE_MODEL_CANDIDATES, MODEL_DISPLAY_NAMES, MODEL_SIZES
        )

    def list_edit_models(self) -> List[ModelInfo]:
        """查询当前账户可用的图生图（编辑）模型。"""
        return self._list_models(
            IMAGE_EDIT_MODEL_CANDIDATES,
            IMAGE_EDIT_DISPLAY_NAMES,
            IMAGE_EDIT_SIZES,
        )

    def _list_models(
        self,
        candidates: List[str],
        names: dict,
        sizes: dict,
    ) -> List[ModelInfo]:
        """查询 /models，按候选白名单过滤出当前账户可用模型。"""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            resp = requests.get(
                f"{self.base}/models", headers=headers, timeout=30
            )
        except requests.RequestException as exc:
            raise ApiError(f"查询可用模型失败：{exc}") from exc

        if resp.status_code != 200:
            raise ApiError(self._error_text(resp))

        available = {m.get("id") for m in resp.json().get("data", [])}
        result: List[ModelInfo] = []
        for mid in candidates:
            if mid in available:
                result.append(
                    ModelInfo(
                        id=mid,
                        name=names.get(mid, mid),
                        sizes=sizes.get(mid, ["1024x1024"]),
                    )
                )
        return result

    # ------------------------------------------------------------------
    # 文本生图
    # ------------------------------------------------------------------
    def generate(
        self,
        prompt: str,
        model: str,
        size: str = "1024x1024",
        num_images: int = 1,
        image: Optional[str] = None,
        negative_prompt: str = "",
        guidance_scale: Optional[float] = None,
        num_inference_steps: Optional[int] = None,
        cfg_scale: Optional[float] = None,
        **extra,
    ) -> GenerationResult:
        """发起文本生图 / 图生图，返回图片字节列表。

        image 不为空时作为参考图（图生图），需为 data URL 或 base64。
        negative_prompt 非空时作为负面提示词。
        以下高级参数为 None 时不发送（由模型用默认值）：
          guidance_scale / num_inference_steps / cfg_scale
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "prompt": prompt,
            "image_size": size,
            "batch_size": max(1, min(num_images, 4)),
        }
        if image:
            payload["image"] = image
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        if guidance_scale is not None:
            payload["guidance_scale"] = guidance_scale
        if num_inference_steps is not None:
            payload["num_inference_steps"] = num_inference_steps
        if cfg_scale is not None:
            payload["cfg_scale"] = cfg_scale
        payload.update(extra)

        try:
            resp = requests.post(
                f"{self.base}/images/generations",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ApiError(f"请求失败：{exc}") from exc

        if resp.status_code != 200:
            raise ApiError(self._error_text(resp))

        data = resp.json()

        # 1) 同步返回：直接解析
        result = self._parse_images(data, prompt)
        if result.images:
            return result

        # 2) 兜底：异步任务模式（响应含 id 但无 images）
        task_id = data.get("id")
        if task_id:
            return self._poll_task(task_id, headers, prompt)

        raise ApiError("未在响应中找到图片数据")

    # ------------------------------------------------------------------
    # 提示词优化（调用轻量文本 LLM，仅硅基流动）
    # ------------------------------------------------------------------
    def optimize_prompt(self, text: str, max_tokens: int = 300) -> str:
        """用文本 LLM 把用户描述优化成高质量英文图像提示词。

        使用轻量模型（默认 Qwen3.5-9B，关闭 thinking 以直接返回结果），
        token 成本极低，复用同一个 API Key。
        """
        system = (
            "你是AI绘画提示词优化专家。把用户的简单描述改写成一段高质量英文"
            "图像生成提示词。只输出优化后的提示词：包含主体、细节、光影、"
            "构图、风格、画质等关键词；不要解释，不要引号，不要其他文字。"
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": PROMPT_OPTIMIZER_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            "max_tokens": max_tokens,
            "enable_thinking": False,
        }
        try:
            resp = requests.post(
                f"{self.base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ApiError(f"提示词优化请求失败：{exc}") from exc

        if resp.status_code != 200:
            raise ApiError(self._error_text(resp))

        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ApiError("提示词优化：响应格式异常") from exc
        content = (content or "").strip()
        if not content:
            raise ApiError("提示词优化：模型未返回内容")
        return content

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _poll_task(self, task_id: str, headers: dict, prompt: str) -> GenerationResult:
        """轮询异步任务直到完成（兼容未来的任务接口）。"""
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                resp = requests.get(
                    f"{self.base}/tasks/{task_id}",
                    headers=headers,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                raise ApiError(f"查询任务失败：{exc}") from exc

            if resp.status_code != 200:
                raise ApiError(self._error_text(resp))

            task = resp.json()
            status = task.get("status")
            if status == "SUCCEEDED":
                result = self._parse_images(task, prompt)
                if result.images:
                    return result
                raise ApiError("任务成功但未找到图片数据")
            if status in ("FAILED", "CANCELED"):
                raise ApiError(f"任务失败：{task.get('reason', status)}")
            time.sleep(2)

        raise ApiError("生成超时，请稍后重试")

    @staticmethod
    def _parse_images(task: dict, prompt: str) -> GenerationResult:
        """从响应中提取图片字节。"""
        result = GenerationResult(prompt=prompt, seed=task.get("seed"))
        for item in task.get("images", []) or task.get("data", []):
            url = item.get("url") or item.get("image_url")
            b64 = item.get("content") or item.get("b64_json")
            if url:
                result.images.append(_download(url))
            elif b64:
                result.images.append(base64.b64decode(b64))
        return result

    @staticmethod
    def _error_text(resp) -> str:
        """从响应提取错误信息。"""
        try:
            body = resp.json()
            msg = (
                body.get("error", {}).get("message")
                or body.get("message")
                or json_dumps(body)
            )
            return f"HTTP {resp.status_code}: {msg}"
        except Exception:
            return f"HTTP {resp.status_code}: {resp.text[:200]}"


class QianwenClient:
    """千问/百炼（DashScope 工作区）图像生成客户端。

    与硅基流动不同，走原生异步 API：
      1) POST .../api/v1/services/aigc/image-generation/generation
         （加 X-DashScope-Async: enable 头，请求体用 input.messages）
      2) 返回 task_id，轮询 .../api/v1/tasks/{id}
      3) 结果在 choices[0].message.content[].image（带签名的 OSS URL）
    """

    def __init__(self, provider: Provider, api_key: str, base_url: str = "") -> None:
        if not api_key:
            raise ApiError("缺少 API Key，请在设置中填写")
        self.provider = provider
        self.api_key = api_key
        # 用户工作区专属 URL，如 ...maas.aliyuncs.com/compatible-mode/v1
        self.base = (base_url or provider.api_base).rstrip("/")
        self.timeout = 90

    def _native_base(self) -> str:
        """从 compatible-mode base 推导原生 API base。"""
        b = self.base
        if "/compatible-mode/v1" in b:
            b = b.replace("/compatible-mode/v1", "")
        return b.rstrip("/")

    @staticmethod
    def _norm_size(size: str) -> str:
        """把 1024x1024 转成 1024*1024（原生 API 用 *）。"""
        s = size.strip()
        if "x" in s and "*" not in s:
            return s.replace("x", "*")
        return s

    # ------------------------------------------------------------------
    # 可用模型查询（走 compatible-mode /models）
    # ------------------------------------------------------------------
    def list_image_models(self) -> List[ModelInfo]:
        return self._list_models(
            QIANWEN_IMAGE_MODEL_CANDIDATES,
            QIANWEN_IMAGE_DISPLAY_NAMES,
            QIANWEN_IMAGE_SIZES,
        )

    def list_edit_models(self) -> List[ModelInfo]:
        return self._list_models(
            QIANWEN_IMAGE_EDIT_MODEL_CANDIDATES,
            QIANWEN_IMAGE_EDIT_DISPLAY_NAMES,
            QIANWEN_IMAGE_EDIT_SIZES,
        )

    def _list_models(self, candidates, names, sizes) -> List[ModelInfo]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            resp = requests.get(f"{self.base}/models", headers=headers, timeout=30)
        except requests.RequestException as exc:
            raise ApiError(f"查询可用模型失败：{exc}") from exc
        if resp.status_code != 200:
            raise ApiError(self._error_text(resp))
        available = {m.get("id") for m in resp.json().get("data", [])}
        result: List[ModelInfo] = []
        for mid in candidates:
            if mid in available:
                result.append(
                    ModelInfo(
                        id=mid,
                        name=names.get(mid, mid),
                        sizes=sizes.get(mid, ["1024x1024"]),
                    )
                )
        return result

    # ------------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------------
    def generate(
        self,
        prompt: str,
        model: str,
        size: str = "1024x1024",
        num_images: int = 1,
        image: Optional[str] = None,
        negative_prompt: str = "",
        **extra,
    ) -> GenerationResult:
        """创建异步任务生成图片，轮询直到完成，返回图片字节。"""
        content = [{"type": "text", "text": prompt}]
        if image:
            content.insert(0, {"type": "image_url", "image_url": {"url": image}})
        messages = [{"role": "user", "content": content}]
        parameters: dict = {"size": self._norm_size(size), "n": max(1, min(num_images, 4))}
        if negative_prompt:
            parameters["negative_prompt"] = negative_prompt

        payload = {
            "model": model,
            "input": {"messages": messages},
            "parameters": parameters,
        }
        endpoint = self._native_base() + "/api/v1/services/aigc/image-generation/generation"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise ApiError(f"提交生成任务失败：{exc}") from exc

        if resp.status_code != 200:
            raise ApiError(self._error_text(resp))
        try:
            task_id = resp.json()["output"]["task_id"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiError("提交任务：响应缺少 task_id") from exc

        return self._poll(task_id, headers, prompt)

    def _poll(self, task_id: str, headers: dict, prompt: str) -> GenerationResult:
        """轮询任务直到成功，取回图片字节。"""
        endpoint = self._native_base() + f"/api/v1/tasks/{task_id}"
        # 任务可能排队较久（wan 系列偶发 2 分钟+），给足 240s
        deadline = time.time() + 240
        while time.time() < deadline:
            try:
                resp = requests.get(
                    endpoint, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=self.timeout
                )
            except requests.RequestException as exc:
                raise ApiError(f"查询任务失败：{exc}") from exc

            if resp.status_code != 200:
                raise ApiError(self._error_text(resp))

            data = resp.json()
            output = data.get("output", {})
            status = output.get("task_status")
            if status == "SUCCEEDED":
                result = self._parse(output, prompt)
                if result.images:
                    return result
                raise ApiError("任务成功但未找到图片数据")
            if status in ("FAILED", "CANCELED"):
                raise ApiError(f"任务失败：{output.get('message', status)}")
            time.sleep(3)

        raise ApiError("生成超时，请稍后重试")

    @staticmethod
    def _parse(output: dict, prompt: str) -> GenerationResult:
        """从成功的任务输出解析图片字节。"""
        result = GenerationResult(prompt=prompt)
        for choice in output.get("choices", []):
            content = (choice.get("message") or {}).get("content", [])
            for item in content or []:
                if isinstance(item, dict) and item.get("type") == "image":
                    url = item.get("image")
                    if url:
                        result.images.append(_download(url))
        return result

    def _error_text(self, resp) -> str:
        try:
            body = resp.json()
            return f"HTTP {resp.status_code}: {body.get('message', resp.text[:200])}"
        except Exception:
            return f"HTTP {resp.status_code}: {resp.text[:200]}"


def _download(url: str) -> bytes:
    """下载远程图片字节。"""
    req = urllib.request.Request(url, headers={"User-Agent": "PixelForge/0.1"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read()


def get_client(
    provider: Provider, api_key: str, base_url: str = ""
):
    """按 Provider 类型返回对应的图像生成客户端。"""
    if provider.id == "qianwen":
        return QianwenClient(provider, api_key, base_url)
    return SiliconFlowClient(provider, api_key)


def json_dumps(obj) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)
