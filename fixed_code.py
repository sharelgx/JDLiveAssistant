# 修复方案：将内层循环体提取为独立方法

# 在 _task_worker 方法内部，替换原有的嵌套循环结构

# ========== 第一步：添加辅助方法 ==========
def _process_page_items(
    self,
    directory: Path,
    duration: float,
    interval: float,
    with_context,
    item_selector: str,
    button_selector: str,
    image_selector: str,
    goods_count: int,
    processed_indices: set,
    processed_skus: set,
    processed_item_indices: set,
    last_processed_index: int,
    last_processed_sku: str,
    last_processed_item_index,
    modal_handled: bool
) -> tuple[int, bool, int, str, any, bool]:
    """
    处理当前页的所有商品
    
    返回: (processed_count, should_continue, last_processed_index, last_processed_sku, last_processed_item_index, modal_handled)
    """
    processed_count = 0
    max_attempts = goods_count * 2
    attempt = 0
    
    while processed_count < goods_count and attempt < max_attempts:
        attempt += 1
        if self.task_stop_event.is_set():
            break
        
        # 等待页面状态更新
        time.sleep(1)
        
        # 查询商品列表
        current_items = with_context(
            lambda ctx: ctx.evaluate(
                """
                ({ itemSelector, buttonSelector }) => {
                    const items = Array.from(document.querySelectorAll(itemSelector));
                    return items.map((item, idx) => {
                        // ... 商品查询逻辑（保持原有代码）...
                        return {
                            index: idx,
                            itemIndex: itemIndex,
                            hasButton: !!button,
                            buttonText: buttonText,
                            isProcessed: isProcessed,
                            sku: sku
                        };
                    });
                }
                """,
                {
                    "itemSelector": item_selector,
                    "buttonSelector": button_selector,
                },
            )
        ) or []
        
        # 按商品编号排序（保持原有逻辑）
        items_with_index = [item for item in current_items if item.get("itemIndex") is not None]
        items_without_index = [item for item in current_items if item.get("itemIndex") is None]
        
        def sort_key(item):
            item_index = item.get("itemIndex")
            if isinstance(item_index, (int, float)):
                return (0, item_index)
            elif isinstance(item_index, str):
                try:
                    num = int(item_index)
                    return (0, num)
                except ValueError:
                    return (1, item_index)
            else:
                return (2, 0)
        
        items_with_index.sort(key=sort_key)
        current_items = items_with_index + items_without_index
        
        # 找到第一个未处理的商品
        next_item = None
        for item_info in current_items:
            index = item_info.get("index", 0)
            button_text = item_info.get("buttonText", "").strip()
            sku = item_info.get("sku", "")
            item_index_raw = item_info.get("itemIndex", None)
            
            # 统一商品编号类型
            item_index = None
            if item_index_raw is not None:
                if isinstance(item_index_raw, (int, float)):
                    item_index = int(item_index_raw)
                elif isinstance(item_index_raw, str):
                    try:
                        item_index = int(item_index_raw)
                    except (ValueError, TypeError):
                        item_index = item_index_raw
                else:
                    item_index = item_index_raw
            
            # 跳过已处理的商品
            if sku and sku in processed_skus:
                continue
            if item_index is not None and item_index in processed_item_indices:
                continue
            if index in processed_indices:
                continue
            
            # 只选择按钮文本是"讲解"的商品
            if button_text == "讲解":
                next_item = item_info
                break
        
        if not next_item:
            self._log("当前页所有商品都已处理完成或没有找到可讲解的商品。")
            break
        
        # 处理找到的商品
        success = self._process_single_item(
            next_item,
            directory,
            duration,
            interval,
            with_context,
            item_selector,
            button_selector,
            image_selector,
            modal_handled
        )
        
        if success:
            # 更新已处理列表
            index = next_item.get("index", 0)
            sku = next_item.get("sku", "")
            item_index = next_item.get("itemIndex")
            
            processed_indices.add(index)
            if item_index is not None:
                if isinstance(item_index, (int, float)):
                    processed_item_indices.add(int(item_index))
                    last_processed_item_index = int(item_index)
                elif isinstance(item_index, str):
                    try:
                        item_index_num = int(item_index)
                        processed_item_indices.add(item_index_num)
                        last_processed_item_index = item_index_num
                    except (ValueError, TypeError):
                        processed_item_indices.add(item_index)
                        last_processed_item_index = item_index
                else:
                    processed_item_indices.add(item_index)
                    last_processed_item_index = item_index
            else:
                last_processed_item_index = None
            
            if sku:
                processed_skus.add(sku)
            
            last_processed_index = index
            last_processed_sku = sku
            
            processed_count += 1
            modal_handled = True  # 第一次处理后标记为已处理
        
        # 等待间隔时间
        if processed_count < goods_count and interval > 0:
            self._log(f"等待 {interval} 秒准备下一场。")
            if self.task_stop_event.wait(interval):
                break
            
            try:
                with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=5000), require_selector=False)
                time.sleep(1)
            except Exception:
                pass
        
        time.sleep(0.5)
    
    return (processed_count, False, last_processed_index, last_processed_sku, last_processed_item_index, modal_handled)


# ========== 第二步：修改主循环结构 ==========
# 在 _task_worker 方法中，将原有的嵌套循环替换为：

while True:  # 外层循环：分页循环
    if self.task_stop_event.is_set():
        break
    
    # 重新统计当前页的商品数量
    count_result = with_context(
        lambda ctx: ctx.evaluate(
            """(selector) => { /* 统计逻辑 */ }""",
            item_selector
        ),
        require_selector=False
    ) or {"total": 0, "valid": 0}
    
    goods_count = count_result.get("valid", 0)
    
    if goods_count == 0:
        self._log(f"倒序第 {page_sequence_label} 页未找到可讲解的商品。")
    else:
        self._log(f"倒序第 {page_sequence_label} 页：共检测到 {goods_count} 个可讲解商品，开始依次处理。")
    
    # 初始化变量
    processed_indices = set()
    processed_skus = set()
    processed_item_indices = set()
    last_processed_index = -1
    last_processed_sku = None
    last_processed_item_index = None
    modal_handled = False
    should_continue_outer_loop = False
    
    # 调用提取的方法处理当前页
    processed_count, _, last_processed_index, last_processed_sku, last_processed_item_index, modal_handled = \
        self._process_page_items(
            directory,
            duration,
            interval,
            with_context,
            item_selector,
            button_selector,
            image_selector,
            goods_count,
            processed_indices,
            processed_skus,
            processed_item_indices,
            last_processed_index,
            last_processed_sku,
            last_processed_item_index,
            modal_handled
        )
    
    # ========== 分页逻辑（原来的第2844-2915行）==========
    # 当前页处理完成，尝试翻到上一页继续处理
    if total_pages > 1:
        pagination_status = _get_pagination_status()
        prev_disabled = pagination_status.get("prevDisabled", True)
        
        if not prev_disabled:
            # 点击上一页
            prev_clicked = with_context(
                lambda ctx: ctx.evaluate("""
                    () => {
                        const prevBtn = document.querySelector('li.ant-pagination-prev button');
                        if (prevBtn && !prevBtn.disabled) {
                            prevBtn.click();
                            return true;
                        }
                        return false;
                    }
                """),
                require_selector=False
            )
            
            if prev_clicked:
                page_sequence_label += 1
                self._log(f"已点击上一页，开始处理倒序第 {page_sequence_label} 页。")
                
                # 等待页面加载
                try:
                    with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=15000), require_selector=False)
                    time.sleep(2)
                except Exception:
                    pass
                
                # 更新当前页码
                pagination_status = _get_pagination_status()
                current_page = pagination_status.get("currentPage", 1)
                
                # 继续外层循环（通过continue）
                continue
            else:
                self._log("上一页按钮不可用，已处理完所有页面。")
        else:
            self._log("已到达第一页，所有页面处理完成。")
    
    # 检查是否需要退出循环
    if self.task_stop_event.is_set():
        self._log("自动讲解任务已被手动停止。")
        break
    
    # 检查是否所有页面都已处理完成
    if total_pages > 1:
        pagination_status = _get_pagination_status()
        prev_disabled = pagination_status.get("prevDisabled", True)
        if prev_disabled:
            self._log("自动讲解任务已完成。")
            break
    else:
        self._log("自动讲解任务已完成。")
        break

# ========== 说明 ==========
# 通过这种重构，我们：
# 1. 将内层循环体提取为 _process_page_items 方法
# 2. 简化了主循环结构，使其更清晰
# 3. 消除了循环嵌套过深的问题
# 4. 使代码更易于维护和调试
