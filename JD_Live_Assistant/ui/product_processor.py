"""商品处理类。"""

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from loguru import logger

from JD_Live_Assistant.ui.page_interactor import PageInteractor


class ProductProcessor:
    """商品处理类。"""

    def __init__(
        self,
        interactor: PageInteractor,
        material_directory: Path,
        duration: float,
        interval: float,
        log_callback: Optional[callable] = None,
        stop_event: Optional[Any] = None,
    ):
        """
        初始化商品处理器。

        Args:
            interactor: 页面交互器
            material_directory: 素材目录
            duration: 讲解时长（秒）
            interval: 间隔时间（秒）
            log_callback: 日志回调函数
            stop_event: 停止事件
        """
        self.interactor = interactor
        self.material_directory = material_directory
        self.duration = duration
        self.interval = interval
        self.log_callback = log_callback or (lambda msg: None)
        self.stop_event = stop_event

        # 处理状态
        self.processed_indices: Set[int] = set()
        self.processed_skus: Set[str] = set()
        self.processed_count = 0

    def _log(self, message: str) -> None:
        """记录日志。"""
        self.log_callback(message)

    def _wait_if_needed(self) -> bool:
        """
        如果需要，等待间隔时间。

        Returns:
            是否应该继续（False 表示应该停止）
        """
        if self.stop_event and self.stop_event.is_set():
            return False

        if self.interval > 0:
            self._log(f"等待 {self.interval} 秒准备下一场。")
            if self.stop_event:
                if self.stop_event.wait(self.interval):
                    return False

            # 间隔等待后，再次确保页面稳定
            try:
                self.interactor.with_context(
                    lambda ctx: ctx.wait_for_load_state("networkidle", timeout=5000),
                    require_selector=False,
                )
                time.sleep(1)
            except Exception:
                pass

        # 重要：在下次循环开始前，再次等待一下，确保页面状态完全更新
        time.sleep(0.5)
        return True

    def _extract_image_url(self, info: Dict[str, Any]) -> Optional[str]:
        """
        从商品信息中提取图片URL。

        Args:
            info: 商品信息字典

        Returns:
            图片URL，如果失败返回 None
        """
        # 尝试多种方式获取图片URL
        image_url = info.get("imageUrl") or info.get("imageDataSrc")

        # 如果没有直接URL，尝试从srcset中提取
        if not image_url:
            srcset = info.get("imageSrcset")
            if srcset:
                # srcset格式通常是 "url1 size1, url2 size2"，取第一个URL
                first_url = srcset.split(',')[0].strip().split()[0]
                if first_url:
                    image_url = first_url

        # 如果还是没有URL，尝试重新查找图片
        if not image_url:
            self._log("未从商品信息中获取到图片URL，尝试重新查找...")
            try:
                image_info = self.interactor.find_product_image(
                    info.get("buttonIndex", 0)
                )

                if image_info:
                    image_url = image_info.get("imageUrl") or image_info.get("imageDataSrc")
                    if not image_url and image_info.get("imageSrcset"):
                        srcset = image_info.get("imageSrcset")
                        first_url = srcset.split(',')[0].strip().split()[0]
                        if first_url:
                            image_url = first_url

                    # 记录重新查找的图片信息
                    if image_info.get("imageAlt"):
                        self._log(f"重新查找的图片alt: {image_info.get('imageAlt')}")
                    if image_info.get("imageParentText"):
                        self._log(f"重新查找的图片父元素文本: {image_info.get('imageParentText')}")
            except Exception as img_exc:
                logger.exception("重新查找图片时发生异常")
                self._log(f"重新查找图片异常：{img_exc}")

        if not image_url:
            return None

        # 处理相对URL
        if not urlparse(image_url).netloc:
            # 获取当前页面URL作为基础URL
            base_url = (
                self.interactor.with_context(lambda ctx: ctx.url, require_selector=False)
                or "https://live.jd.com"
            )
            image_url = urljoin(base_url, image_url)

        return image_url

    def _check_ai_shouka_image(self, info: Dict[str, Any]) -> bool:
        """
        检查是否是AI手卡图片。

        Args:
            info: 商品信息字典

        Returns:
            如果是AI手卡图片返回 True
        """
        image_alt_check = info.get("imageAlt", "")
        if image_alt_check:
            self._log(f"图片alt属性: {image_alt_check}")
            if 'AI' in image_alt_check and '手卡' in image_alt_check:
                self._log(f"警告：图片alt同时包含'AI'和'手卡'关键词，跳过下载：{image_alt_check}")
                return True
        return False

    def _download_image(self, url: str, destination: Path) -> bool:
        """
        下载图片。

        Args:
            url: 图片URL
            destination: 保存路径

        Returns:
            是否成功
        """
        try:
            req = Request(url)
            req.add_header("User-Agent", "Mozilla/5.0")
            with urlopen(req, timeout=30) as response:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with open(destination, "wb") as f:
                    f.write(response.read())
            return True
        except Exception as e:
            logger.exception("下载图片失败")
            self._log(f"下载图片失败：{e}")
            return False

    def process_product(
        self, index: int, goods_count: int
    ) -> tuple[bool, Optional[str]]:
        """
        处理单个商品。

        Args:
            index: 商品索引
            goods_count: 商品总数

        Returns:
            (是否成功, SKU或None)
        """
        # 检查是否已处理
        if index in self.processed_indices:
            self._log(f"商品 {index} 已处理，跳过。")
            return False, None

        # 获取商品信息
        info = self.interactor.get_product_info(index)
        if not info:
            self._log(f"未能获取第 {self.processed_count + 1} 个商品信息，跳过。")
            self.processed_indices.add(index)
            self.processed_count += 1
            return False, None

        title = info.get("title", f"商品 {index + 1}")
        self._log(f"获取商品信息：{title}")

        # 检查按钮
        if not info.get("buttonFound"):
            self._log(f"跳过商品 {index}：未找到'讲解'按钮")
            self.processed_indices.add(index)
            self.processed_count += 1
            return False, None

        # 提取图片URL
        image_url = self._extract_image_url(info)
        if not image_url:
            self._log(f"[{self.processed_count + 1}/{goods_count}] 未获取到图片URL，跳过下载。")
            self.processed_indices.add(index)
            self.processed_count += 1
            return False, None

        # 检查是否是AI手卡图片
        if self._check_ai_shouka_image(info):
            self.processed_indices.add(index)
            self.processed_count += 1
            return False, None

        # 下载图片
        image_filename = f"{index + 1}.jpg"
        image_path = self.material_directory / image_filename

        if not self._download_image(image_url, image_path):
            self.processed_indices.add(index)
            self.processed_count += 1
            return False, None

        self._log(f"[{self.processed_count + 1}/{goods_count}] 已下载图片：{image_filename}")

        # 点击"讲解"按钮
        click_result = self.interactor.click_explain_button(index)
        if not click_result.get("success"):
            self._log(f"点击'讲解'按钮失败：{click_result.get('reason', 'Unknown')}")
            self.processed_indices.add(index)
            self.processed_count += 1
            return False, None

        self._log(f"已点击'讲解'按钮")

        # 等待讲解时长
        if self.stop_event:
            if self.stop_event.wait(self.duration):
                return False, None
        else:
            time.sleep(self.duration)

        # 记录处理状态
        sku = info.get("title", "")
        self.processed_indices.add(index)
        if sku:
            self.processed_skus.add(sku)
        self.processed_count += 1

        return True, sku

