"""图片生成服务。

把 API 客户端、Key 管理、历史记录、文件保存整合成一个高层接口，
供 UI 层调用，避免 UI 直接接触底层细节。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, List, Optional

from pixelforge.core.api_client import get_client
from pixelforge.core.storage import HistoryRecord, HistoryStore
from pixelforge.models.gen_modes import mode_kwargs
from pixelforge.models.providers import ModelInfo, Provider, get_provider
from pixelforge.security.key_manager import KeyManager


class ImageService:
    """面向 UI 的图片生成服务门面。"""

    def __init__(self, config, key_manager: KeyManager, history: HistoryStore) -> None:
        self.config = config
        self.key_manager = key_manager
        self.history = history
        self._migrate_legacy_favorites()

    # ------------------------------------------------------------------
    # Provider 工具
    # ------------------------------------------------------------------
    def _provider_id(self) -> str:
        return self.config.get("model.provider", "siliconflow")

    def _base_url(self) -> str:
        """当前 Provider 的自定义 base URL（如千问工作区 URL）。"""
        return self.config.get(
            f"providers.{self._provider_id()}.base_url", ""
        ) or ""

    def _custom_model_ids(self) -> List[str]:
        """自定义厂商：用户在设置中以逗号分隔录入的模型 ID。"""
        raw = self.config.get(f"providers.{self._provider_id()}.models", "") or ""
        return [m.strip() for m in raw.split(",") if m.strip()]

    def _client(self):
        """按当前 Provider 创建对应客户端（无 Key 时抛异常）。"""
        api_key = self.key_manager.load(self._provider_id())
        if not api_key:
            raise RuntimeError("未设置 API Key，请先在设置中填写")
        provider = get_provider(self._provider_id()) or get_provider("siliconflow")
        return get_client(
            provider, api_key, self._base_url(),
            model_ids=self._custom_model_ids(),
        )

    def _split_batches(self, client, num_images: int) -> List[int]:
        """把请求张数拆成多次调用的张数列表。

        部分厂商单次只返回一张（如 Seedream/智谱/混元），由服务层
        循环调用补足用户要的张数。
        """
        per = max(1, getattr(client, "max_batch", 1))
        batches: List[int] = []
        remaining = max(1, num_images)
        while remaining > 0:
            n = min(per, remaining)
            batches.append(n)
            remaining -= n
        return batches

    def _client_or_none(self):
        """按当前 Provider 创建客户端；无 Key 返回 None。"""
        api_key = self.key_manager.load(self._provider_id())
        if not api_key:
            return None
        provider = get_provider(self._provider_id()) or get_provider("siliconflow")
        return get_client(
            provider, api_key, self._base_url(),
            model_ids=self._custom_model_ids(),
        )

    # ------------------------------------------------------------------
    # Key
    # ------------------------------------------------------------------
    def save_api_key(self, api_key: str, provider_id: str | None = None) -> None:
        """保存指定 Provider 的 API Key。"""
        provider_id = provider_id or self._provider_id()
        self.key_manager.save(api_key, provider_id)
        self.config.set("model.provider", provider_id)
        self.config.save()

    def has_api_key(self) -> bool:
        return self.key_manager.has_key(self._provider_id())

    # ------------------------------------------------------------------
    # 可用模型
    # ------------------------------------------------------------------
    def list_available_models(self) -> List[ModelInfo]:
        """查询当前账户可用的图像模型；未配置 Key 或无权限时返回空列表。"""
        client = self._client_or_none()
        if not client:
            return []
        try:
            return client.list_image_models()
        except Exception:  # noqa: BLE001
            return []

    def list_available_edit_models(self) -> List[ModelInfo]:
        """查询当前账户可用的图生图（编辑）模型。"""
        client = self._client_or_none()
        if not client:
            return []
        try:
            return client.list_edit_models()
        except Exception:  # noqa: BLE001
            return []

    # ------------------------------------------------------------------
    # 提示词优化
    # ------------------------------------------------------------------
    def optimize_prompt(self, text: str) -> str:
        """用文本 LLM 优化提示词（复用当前 Provider 的 Key）。

        未配置 Key 时抛异常。
        """
        client = self._client()
        if not hasattr(client, "optimize_prompt"):
            raise RuntimeError("当前平台暂不支持提示词优化")
        return client.optimize_prompt(text)

    # ------------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------------
    def generate(
        self,
        prompt: str,
        model_id: str,
        size: str = "1024x1024",
        num_images: int = 1,
        negative_prompt: str = "",
        guidance_scale: float | None = None,
        num_inference_steps: int | None = None,
        cfg_scale: float | None = None,
        mode: str | None = None,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> List[Path]:
        """生成图片并保存到本地，返回保存路径列表。

        同时写入历史记录（含用时）。若未配置 Key 则抛出异常。
        mode 为生成模式 ID（快速/标准/创造），其预设参数与显式传入的
        高级参数合并（显式值优先）。
        progress_cb(已开始批序号, 总批数) 在每批调用前触发，用于 UI 进度提示；
        单批请求（多数场景）也会触发一次 (1, 1)。
        """
        client = self._client()
        presets = mode_kwargs(mode)
        saved: List[Path] = []
        batches = self._split_batches(client, num_images)
        for batch_no, batch_n in enumerate(batches, start=1):
            if progress_cb:
                progress_cb(batch_no, len(batches))
            started = time.monotonic()
            result = client.generate(
                prompt, model_id, size, batch_n,
                negative_prompt=negative_prompt,
                guidance_scale=guidance_scale
                if guidance_scale is not None
                else presets.get("guidance_scale"),
                num_inference_steps=num_inference_steps
                if num_inference_steps is not None
                else presets.get("num_inference_steps"),
                cfg_scale=cfg_scale,
            )
            duration = round(time.monotonic() - started, 1)
            for img_bytes in result.images:
                path = self._save_image(img_bytes)
                saved.append(path)
                self.history.add(
                    HistoryRecord(
                        prompt=prompt,
                        model=model_id,
                        size=size,
                        path=str(path),
                        seed=result.seed,
                        duration=duration,
                    )
                )
        return saved

    # ------------------------------------------------------------------
    # 图生图
    # ------------------------------------------------------------------
    def image_to_image(
        self,
        prompt: str,
        model_id: str,
        ref_image_path: str | Path,
        size: str = "1024x1024",
        num_images: int = 1,
        negative_prompt: str = "",
        guidance_scale: float | None = None,
        num_inference_steps: int | None = None,
        cfg_scale: float | None = None,
        mode: str | None = None,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> List[Path]:
        """图生图：以参考图 + 文本指令生成图片，返回保存路径列表。

        progress_cb 语义同 generate()。
        """
        client = self._client()
        image_data = self._to_data_url(ref_image_path)
        presets = mode_kwargs(mode)
        saved: List[Path] = []
        batches = self._split_batches(client, num_images)
        for batch_no, batch_n in enumerate(batches, start=1):
            if progress_cb:
                progress_cb(batch_no, len(batches))
            started = time.monotonic()
            result = client.generate(
                prompt, model_id, size, batch_n,
                image=image_data, negative_prompt=negative_prompt,
                guidance_scale=guidance_scale
                if guidance_scale is not None
                else presets.get("guidance_scale"),
                num_inference_steps=num_inference_steps
                if num_inference_steps is not None
                else presets.get("num_inference_steps"),
                cfg_scale=cfg_scale,
            )
            duration = round(time.monotonic() - started, 1)
            for img_bytes in result.images:
                path = self._save_image(img_bytes)
                saved.append(path)
                self.history.add(
                    HistoryRecord(
                        prompt=prompt,
                        model=model_id,
                        size=size,
                        path=str(path),
                        seed=result.seed,
                        duration=duration,
                    )
                )
        return saved

    @staticmethod
    def _to_data_url(path: str | Path) -> str:
        """把本地图片转成 data URL（base64）。"""
        import base64
        import mimetypes

        path = Path(path)
        mime = mimetypes.guess_type(str(path))[0] or "image/png"
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{b64}"

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _save_image(self, data: bytes) -> Path:
        """把图片字节保存到图片目录，返回路径。"""
        image_dir = self.config.effective_image_dir
        image_dir.mkdir(parents=True, exist_ok=True)

        # 用时间戳命名，避免重名
        import uuid
        from datetime import datetime

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"{stamp}_{uuid.uuid4().hex[:6]}.png"
        path = image_dir / name
        path.write_bytes(data)
        return path

    # ------------------------------------------------------------------
    # 收藏夹
    # ------------------------------------------------------------------
    @property
    def favorite_dir(self) -> Path:
        """收藏夹目录：软件数据目录下的 Like/。

        与图片存储路径解耦（固定跟软件走），避免多项目副本或
        修改图片路径后收藏位置错乱。
        """
        return self.config.config_dir / "Like"

    def _migrate_legacy_favorites(self) -> None:
        """旧版收藏存在 图片目录/Like，启动时一次性搬到数据目录 Like。

        复制而非移动（旧目录原样保留由用户处置）；同名文件跳过，
        因此重复启动无副作用。任何异常静默忽略，不阻断启动。
        """
        try:
            import shutil

            legacy = self.config.effective_image_dir / "Like"
            new = self.favorite_dir
            if not legacy.is_dir() or legacy.resolve() == new.resolve():
                return
            new.mkdir(parents=True, exist_ok=True)
            for f in legacy.iterdir():
                if f.is_file() and not (new / f.name).exists():
                    shutil.copy2(f, new / f.name)
        except Exception:  # noqa: BLE001
            pass

    def favorite(self, image_path: str | Path) -> Path:
        """把图片复制到收藏夹（Like）目录，返回收藏后的路径。

        采用复制而非移动，保留原图与生成历史，不影响已有功能。
        """
        import shutil

        src = Path(image_path)
        if not src.exists():
            raise FileNotFoundError(f"图片不存在：{src}")

        like_dir = self.favorite_dir
        like_dir.mkdir(parents=True, exist_ok=True)

        dst = like_dir / src.name
        if dst.exists():
            stem, suffix = src.stem, src.suffix
            i = 1
            while dst.exists():
                dst = like_dir / f"{stem}_{i}{suffix}"
                i += 1
        shutil.copy2(src, dst)
        return dst

    def is_favorited(self, image_path: str | Path) -> bool:
        """判断某张图片是否已在收藏夹（同名文件是否存在）。"""
        like_dir = self.favorite_dir
        if not like_dir.exists():
            return False
        return (like_dir / Path(image_path).name).exists()

    def unfavorite(self, image_path: str | Path) -> bool:
        """从收藏夹移除该图片（删除副本，保留原图）。返回是否删除成功。"""
        like_dir = self.favorite_dir
        dst = like_dir / Path(image_path).name
        if dst.exists():
            dst.unlink()
            return True
        return False

