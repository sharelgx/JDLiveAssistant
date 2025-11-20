# 需要修复的源代码片段
# 文件：JD_Live_Assistant/ui/main_window.py
# 问题：第2904、2912、2915行的 break 语句不在循环中

# ========== 外层循环开始（第1230行）==========
            while True:
                if self.task_stop_event.is_set():
                    break
                
                # 重新统计当前页的商品数量
                # ... 统计代码 ...
                
                # 初始化变量
                processed_count = 0
                max_attempts = goods_count * 2
                attempt = 0
                modal_handled = False
                processed_indices = set()
                processed_skus = set()
                processed_item_indices = set()
                last_processed_index = -1
                last_processed_sku = None
                last_processed_item_index = None
                should_continue_outer_loop = False

                # ========== 内层循环开始（第1293行）==========
                while processed_count < goods_count and attempt < max_attempts:
                    attempt += 1
                    if self.task_stop_event.is_set():
                        break
                    
                    # 每次循环都重新查询商品列表，因为点击后页面可能变化
                    # 等待一下，确保页面状态已更新
                    time.sleep(1)  # 增加等待时间，确保页面状态更新
                
                    # 记录当前页码，用于调试
                    if total_pages > 1:
                        pagination_status_debug = _get_pagination_status()
                        current_page_debug = pagination_status_debug.get("currentPage", 1)
                        self._log(f"重新查询商品列表前，当前页码: {current_page_debug}/{total_pages}")
                        logger.info(f"重新查询商品列表前，当前页码: {current_page_debug}/{total_pages}")
                    
                    # 查询商品列表
                    current_items = with_context(
                        # ... 查询逻辑 ...
                    ) or []
                    
                    # 按商品编号排序
                    # ... 排序逻辑 ...
                    
                    # 找到第一个未处理的商品
                    next_item = None
                    # ... 查找逻辑 ...
                    
                    if not next_item:
                        self._log("当前页所有商品都已处理完成或没有找到可讲解的商品。")
                        logger.info("当前页所有商品都已处理完成或没有找到可讲解的商品。")
                        break
                    
                    # 处理商品
                    index = next_item.get("index", 0)
                    # ... 处理商品的完整逻辑 ...
                    # 包括：下载图片、点击讲解按钮、等待、停止等
                    
                    # 处理完成后，将索引、商品编号和SKU添加到已处理列表
                    processed_indices.add(index)
                    # ... 记录已处理商品 ...
                    
                    processed_count += 1

                    # 如果还有商品未处理，等待间隔时间
                    if processed_count < goods_count and interval > 0:
                        self._log(f"等待 {interval} 秒准备下一场。")
                        if self.task_stop_event.wait(interval):
                            break
                        
                        # 间隔等待后，再次确保页面稳定
                        try:
                            with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=5000), require_selector=False)
                            time.sleep(1)  # 增加等待时间，确保页面状态更新
                        except Exception:
                            pass
                    
                    # 重要：在下次循环开始前，再次等待一下，确保页面状态完全更新
                    # 这样重新查询商品列表时，第一个商品的状态应该已经更新（不再是"讲解"）
                    time.sleep(0.5)
                    
                    # 注意：这里不翻页，只是继续循环处理当前页的下一个商品
                    # 翻页逻辑应该在 while 循环结束后执行（当 processed_count >= goods_count 时）
                
                # ========== 内层循环结束（第2842行之后）==========
                # while processed_count < goods_count 循环结束后，处理完当前页所有商品，尝试翻到上一页继续处理
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
                            logger.info(f"已点击上一页，开始处理倒序第 {page_sequence_label} 页。")
                            # 等待页面加载
                            try:
                                with_context(lambda ctx: ctx.wait_for_load_state("networkidle", timeout=15000), require_selector=False)
                                time.sleep(2)  # 等待页面渲染
                            except Exception:
                                pass
                            
                            # 更新当前页码
                            pagination_status = _get_pagination_status()
                            current_page = pagination_status.get("currentPage", 1)
                            
                            # 重新获取商品列表，继续处理（继续外层 while True 循环）
                            # 重置 processed_count 和 attempt，以便处理新页面的商品
                            processed_count = 0
                            attempt = 0
                            # 标记需要继续外层循环，在外层循环中检查这个标志
                            should_continue_outer_loop = True
                        else:
                            self._log("上一页按钮不可用，已处理完所有页面。")
                            logger.info("上一页按钮不可用，已处理完所有页面。")
                    else:
                        self._log("已到达第一页，所有页面处理完成。")
                        logger.info("已到达第一页，所有页面处理完成。")
            
            # ========== 问题代码部分（第2894-2915行）==========
            # 检查是否需要继续外层循环（翻页后）
            # 如果翻页了，重置标志并继续外层循环
            if should_continue_outer_loop:
                should_continue_outer_loop = False
                # 重置变量后，外层 while True 循环会自动继续
                # 不需要 continue，因为循环会自动继续
                pass
            elif self.task_stop_event.is_set():
                # 检查任务是否被停止
                self._log("自动讲解任务已被手动停止。")
                break  # ❌ 第2904行：Python 认为这个 break 不在循环中
            else:
                # 检查是否所有页面都已处理完成
                if total_pages > 1:
                    pagination_status = _get_pagination_status()
                    prev_disabled = pagination_status.get("prevDisabled", True)
                    if prev_disabled:
                        self._log("自动讲解任务已完成。")
                        break  # ❌ 第2912行：Python 认为这个 break 不在循环中
                else:
                    self._log("自动讲解任务已完成。")
                    break  # ❌ 第2915行：Python 认为这个 break 不在循环中
        finally:
            controller.disconnect()
            self.task_thread = None
            self.task_stop_event.clear()
            self.after(0, lambda: self._set_task_running(False))

