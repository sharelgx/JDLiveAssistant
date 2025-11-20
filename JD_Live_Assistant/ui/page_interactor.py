"""页面交互处理类。"""

from typing import Any, Callable, Dict, Optional

from loguru import logger
from playwright.sync_api import Page

from JD_Live_Assistant.core.automation import BrowserController
from JD_Live_Assistant.ui.page_scripts import PageScripts


class PageInteractor:
    """页面交互处理类。"""

    def __init__(self, controller: BrowserController, item_selector: str):
        """
        初始化页面交互器。

        Args:
            controller: 浏览器控制器
            item_selector: 商品项选择器
        """
        self.controller = controller
        self.item_selector = item_selector

    def with_context(
        self, callback: Callable[[Page], Optional[Any]], require_selector: bool = True
    ) -> Optional[Any]:
        """
        在页面上下文中执行回调。

        Args:
            callback: 回调函数
            require_selector: 是否需要等待选择器

        Returns:
            回调函数的返回值
        """
        def run(page: Page) -> Optional[Any]:
            # 先尝试主页面
            try:
                # 等待页面加载完成
                page.wait_for_load_state("networkidle", timeout=10000)
                if require_selector:
                    page.wait_for_selector(self.item_selector, timeout=10000, state="attached")
                return callback(page)
            except Exception:
                if not require_selector:
                    # 如果不需要选择器，直接返回主页面
                    return callback(page)
                pass

            # 如果主页面没有，尝试所有frames
            if require_selector:
                frames = page.frames
                for candidate in frames:
                    try:
                        candidate.wait_for_selector(self.item_selector, timeout=5000, state="attached")
                        return callback(candidate)
                    except Exception:
                        continue
                raise RuntimeError("未在任何 frame 中检测到商品列表。")
            else:
                # 不需要选择器时，返回主页面
                return callback(page)

        return self.controller.perform(run)

    def get_pagination_status(self) -> Dict[str, Any]:
        """
        获取分页状态信息。

        Returns:
            分页状态字典
        """
        result = self.with_context(
            lambda ctx: ctx.evaluate(PageScripts.get_pagination_status()),
            require_selector=False,
        )

        if not result:
            return {
                "hasPagination": False,
                "pageCount": 1,
                "currentPage": 1,
                "prevDisabled": True,
                "nextDisabled": True,
            }
        return result

    def go_to_page(self, target_page: int) -> bool:
        """
        跳转到指定页码。

        Args:
            target_page: 目标页码

        Returns:
            是否成功
        """
        if target_page <= 0:
            return False

        clicked = self.with_context(
            lambda ctx, tp=target_page: ctx.evaluate(PageScripts.go_to_page(), tp),
            require_selector=False,
        )

        if not clicked:
            return False

        try:
            self.with_context(
                lambda ctx: ctx.wait_for_load_state("networkidle", timeout=15000),
                require_selector=False,
            )
        except Exception:
            pass

        import time
        time.sleep(1)
        return True

    def click_next_page(self) -> bool:
        """
        点击下一页。

        Returns:
            是否成功
        """
        clicked = self.with_context(
            lambda ctx: ctx.evaluate(PageScripts.click_next_page()),
            require_selector=False,
        )

        if not clicked:
            return False

        try:
            self.with_context(
                lambda ctx: ctx.wait_for_load_state("networkidle", timeout=15000),
                require_selector=False,
            )
        except Exception:
            pass

        import time
        time.sleep(2)
        return True

    def get_product_info(self, index: int) -> Optional[Dict[str, Any]]:
        """
        获取商品信息。

        Args:
            index: 商品索引

        Returns:
            商品信息字典，如果失败返回 None
        """
        try:
            result = self.with_context(
                lambda ctx, idx=index: ctx.evaluate(
                    PageScripts.get_product_info(),
                    {
                        "itemSelector": self.item_selector,
                        "imageSelector": PageScripts.IMAGE_SELECTOR,
                        "buttonSelector": PageScripts.BUTTON_SELECTOR,
                        "index": idx,
                    },
                )
            )
            return result
        except Exception as e:
            logger.exception("获取商品信息失败")
            return None

    def find_product_image(self, index: int) -> Optional[Dict[str, Any]]:
        """
        查找商品图片。

        Args:
            index: 商品索引

        Returns:
            图片信息字典，如果失败返回 None
        """
        try:
            result = self.with_context(
                lambda ctx, idx=index: ctx.evaluate(
                    PageScripts.find_product_image(),
                    {
                        "itemSelector": self.item_selector,
                        "imageSelector": PageScripts.IMAGE_SELECTOR,
                        "index": idx,
                    },
                )
            )
            return result
        except Exception as e:
            logger.exception("查找商品图片失败")
            return None

    def click_explain_button(self, index: int) -> Dict[str, Any]:
        """
        点击"讲解"按钮。

        Args:
            index: 商品索引

        Returns:
            操作结果字典
        """
        try:
            result = self.with_context(
                lambda ctx, idx=index: ctx.evaluate(
                    PageScripts.click_explain_button(),
                    {
                        "itemSelector": self.item_selector,
                        "buttonSelector": PageScripts.BUTTON_SELECTOR,
                        "index": idx,
                    },
                )
            )
            return result or {"success": False, "reason": "Unknown error"}
        except Exception as e:
            logger.exception("点击讲解按钮失败")
            return {"success": False, "reason": str(e)}

    def get_product_list(self) -> list:
        """
        获取商品列表。

        Returns:
            商品列表
        """
        try:
            result = self.with_context(
                lambda ctx: ctx.evaluate(
                    PageScripts.get_product_list(),
                    {
                        "itemSelector": self.item_selector,
                        "buttonSelector": PageScripts.BUTTON_SELECTOR,
                    },
                )
            )
            return result or []
        except Exception as e:
            logger.exception("获取商品列表失败")
            return []

