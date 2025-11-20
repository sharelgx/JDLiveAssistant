"""页面交互的 JavaScript 脚本集合。"""


class PageScripts:
    """页面交互的 JavaScript 脚本。"""

    # 选择器常量
    ITEM_SELECTOR = (
        "tr.ant-table-row, "
        "div.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-skuContainer, "
        "div.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-wrapper"
    )
    IMAGE_SELECTOR = "img.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-img"
    BUTTON_SELECTOR = ".antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-selectBtn"

    @staticmethod
    def get_pagination_status() -> str:
        """获取分页状态的 JavaScript 代码。"""
        return """
        () => {
            const pagination = document.querySelector('.ant-pagination');
            if (!pagination) {
                return {
                    hasPagination: false,
                    pageCount: 1,
                    currentPage: 1,
                    prevDisabled: true,
                    nextDisabled: true,
                };
            }

            const pageItems = Array.from(pagination.querySelectorAll('li.ant-pagination-item'));
            const pageNumbers = pageItems
                .map((item) => {
                    const anchor = item.querySelector('a');
                    const text = anchor ? anchor.textContent : item.textContent;
                    return text ? parseInt(text.trim(), 10) : NaN;
                })
                .filter((num) => !Number.isNaN(num))
                .sort((a, b) => a - b);

            const activeItem = pagination.querySelector('li.ant-pagination-item-active');
            let currentPage = 1;
            if (activeItem) {
                const anchor = activeItem.querySelector('a');
                const text = anchor ? anchor.textContent : activeItem.textContent;
                if (text) {
                    const parsed = parseInt(text.trim(), 10);
                    if (!Number.isNaN(parsed)) {
                        currentPage = parsed;
                    }
                }
            }

            const pageCount = pageNumbers.length > 0 ? Math.max(...pageNumbers) : 1;
            const prev = pagination.querySelector('li.ant-pagination-prev');
            const next = pagination.querySelector('li.ant-pagination-next');
            const prevDisabled = !!(prev && prev.classList.contains('ant-pagination-disabled'));
            const nextDisabled = !!(next && next.classList.contains('ant-pagination-disabled'));

            return {
                hasPagination: pageCount > 1,
                pageCount,
                currentPage,
                prevDisabled,
                nextDisabled,
            };
        }
        """

    @staticmethod
    def go_to_page() -> str:
        """跳转到指定页码的 JavaScript 代码。"""
        return """
        (targetPage) => {
            const direct = document.querySelector(`li.ant-pagination-item-${targetPage} a`);
            if (direct) {
                direct.click();
                return true;
            }
            const links = Array.from(document.querySelectorAll('li.ant-pagination-item a'));
            const target = links.find((link) => link.textContent && link.textContent.trim() === String(targetPage));
            if (target) {
                target.click();
                return true;
            }
            return false;
        }
        """

    @staticmethod
    def click_next_page() -> str:
        """点击下一页的 JavaScript 代码。"""
        return """
        () => {
            const nextBtn = document.querySelector('li.ant-pagination-next button');
            if (nextBtn && !nextBtn.disabled) {
                nextBtn.click();
                return true;
            }
            return false;
        }
        """

    @staticmethod
    def get_product_info() -> str:
        """获取商品信息的 JavaScript 代码。"""
        return """
        ({ itemSelector, buttonSelector, imageSelector, index }) => {
            const items = Array.from(document.querySelectorAll(itemSelector));
            const item = items[index];
            if (!item) {
                return null;
            }
            
            // 查找"讲解"按钮 - 尝试多种方式
            // 注意：要排除下拉菜单的触发按钮（三个点...），只选择文本严格为"讲解"的按钮
            let button = null;
            
            // 辅助函数：检查是否是下拉菜单的触发按钮（三个点）
            const isDropdownTrigger = (node) => {
                const text = (node.textContent || '').trim();
                // 检查是否是三个点或包含下拉菜单相关的类名
                if (text === '...' || text === '⋯' || text === '⋮' || text.length <= 2) {
                    return true;
                }
                // 检查是否包含下拉菜单相关的类名
                const className = node.className || '';
                if (typeof className === 'string') {
                    if (className.includes('dropdown') || className.includes('more') || 
                        className.includes('menu') || className.includes('trigger')) {
                        return true;
                    }
                }
                // 检查父元素是否是下拉菜单
                let parent = node.parentElement;
                let checkCount = 0;
                while (parent && checkCount < 3) {
                    const parentClass = parent.className || '';
                    if (typeof parentClass === 'string') {
                        if (parentClass.includes('dropdown') || parentClass.includes('menu')) {
                            return true;
                        }
                    }
                    parent = parent.parentElement;
                    checkCount++;
                }
                return false;
            };
            
            // 辅助函数：获取元素的完整文本（包括内部所有子元素的文本）
            const getFullText = (node) => {
                if (!node) return '';
                // 先尝试获取 textContent（包含所有子元素的文本）
                let text = (node.textContent || '').trim();
                // 如果 textContent 为空，尝试获取 innerText
                if (!text) {
                    text = (node.innerText || '').trim();
                }
                // 如果还是为空，尝试查找内部的 span 等元素
                if (!text) {
                    const innerSpan = node.querySelector('span');
                    if (innerSpan) {
                        text = (innerSpan.textContent || innerSpan.innerText || '').trim();
                    }
                }
                return text;
            };
            
            // 方式1: 查找包含"讲解"文本的span，且类名包含selectBtn
            // 根据HTML结构：<span class="antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-selectBtn">讲解</span>
            const selectBtnSpans = Array.from(item.querySelectorAll('span.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-selectBtn'));
            button = selectBtnSpans.find((span) => {
                const text = getFullText(span);
                // 严格匹配：文本必须是"讲解"
                return text === "讲解";
            });
            
            // 方式2: 如果没找到，查找包含"讲解"文本的span，但排除下拉菜单
            if (!button) {
                const allSpans = Array.from(item.querySelectorAll('span'));
                button = allSpans.find((span) => {
                    const text = getFullText(span);
                    // 严格匹配：文本必须是"讲解"，不能是下拉菜单触发按钮
                    return text === "讲解" && !isDropdownTrigger(span);
                });
            }
            
            // 方式3: 如果还是没找到，在整个item中查找，但排除下拉菜单
            if (!button) {
                const allButtons = Array.from(item.querySelectorAll('button, span, div, a'));
                button = allButtons.find((node) => {
                    const text = getFullText(node);
                    // 严格匹配：文本必须是"讲解"，不能是下拉菜单触发按钮
                    return text === "讲解" && !isDropdownTrigger(node);
                });
            }
            
            // 查找图片
            let image = null;
            
            // 辅助函数：检查图片是否是"AI手卡"图片
            const isAIShoukaImage = (img) => {
                const alt = (img.alt || '').trim();
                const src = (img.src || img.getAttribute('data-src') || '').toLowerCase();
                const title = (img.title || '').trim();
                
                // 检查alt、src、title中是否包含"AI"和"手卡"
                if (alt.includes('AI') && alt.includes('手卡')) return true;
                if (src.includes('ai') && (src.includes('shouka') || src.includes('手卡'))) return true;
                if (title.includes('AI') && title.includes('手卡')) return true;
                
                // 检查父元素或兄弟元素的文本中是否包含"AI手卡"
                let parent = img.parentElement;
                let checkCount = 0;
                while (parent && checkCount < 3) {
                    const parentText = (parent.textContent || '').trim();
                    if (parentText.includes('AI') && parentText.includes('手卡')) {
                        return true;
                    }
                    parent = parent.parentElement;
                    checkCount++;
                }
                
                return false;
            };
            
            // 方式1: 使用特定选择器，检查alt是否为"商品图"，且不是"AI手卡"图片
            image = item.querySelector(imageSelector);
            if (image && (isAIShoukaImage(image) || (image.alt || '').trim() !== '商品图')) {
                image = null;
            }
            
            // 方式2: 查找item中所有img，只选择alt为"商品图"的图片，排除"AI手卡"图片
            if (!image) {
                const images = Array.from(item.querySelectorAll("img"));
                image = images.find(img => {
                    const alt = (img.alt || '').trim();
                    const src = img.src || img.getAttribute('data-src') || '';
                    // 必须是"商品图"，且不是"AI手卡"图片
                    return src && src.trim() !== '' && 
                           alt === '商品图' && 
                           !isAIShoukaImage(img);
                });
            }
            
            // 获取商品标题
            let titleText = '';
            if (image && image.alt) {
                titleText = image.alt;
            } else {
                // 尝试从item中查找文本节点
                const textNodes = Array.from(item.childNodes)
                    .filter(node => node.nodeType === 3) // 文本节点
                    .map(node => node.textContent?.trim())
                    .filter(text => text && text.length > 0 && text !== '讲解');
                if (textNodes.length > 0) {
                    titleText = textNodes[0];
                }
            }
            
            return {
                imageUrl: image ? image.src : null,
                imageSrcset: image ? image.srcset : null,
                imageDataSrc: image ? image.getAttribute('data-src') : null,
                imageAlt: image ? (image.alt || '') : null,
                imageTitle: image ? (image.title || '') : null,
                imageSrc: image ? image.src : null,
                imageClassName: image ? image.className : null,
                imageParentText: image && image.parentElement ? (image.parentElement.textContent || '').substring(0, 100) : null,
                title: titleText || `商品 ${index + 1}`,
                buttonIndex: index,
                buttonFound: !!button
            };
        }
        """

    @staticmethod
    def find_product_image() -> str:
        """查找商品图片的 JavaScript 代码。"""
        return """
        ({ itemSelector, imageSelector, index }) => {
            const items = Array.from(document.querySelectorAll(itemSelector));
            const item = items[index];
            if (!item) {
                return null;
            }
            
            // 查找图片 - 只选择alt为"商品图"的图片，排除"AI手卡图片"等其他图片
            let image = null;
            
            // 辅助函数：检查图片是否是"AI手卡"图片
            const isAIShoukaImage = (img) => {
                const alt = (img.alt || '').trim();
                const src = (img.src || img.getAttribute('data-src') || '').toLowerCase();
                const title = (img.title || '').trim();
                
                // 检查alt、src、title中是否包含"AI"和"手卡"
                if (alt.includes('AI') && alt.includes('手卡')) return true;
                if (src.includes('ai') && (src.includes('shouka') || src.includes('手卡'))) return true;
                if (title.includes('AI') && title.includes('手卡')) return true;
                
                // 检查父元素或兄弟元素的文本中是否包含"AI手卡"
                let parent = img.parentElement;
                let checkCount = 0;
                while (parent && checkCount < 3) {
                    const parentText = (parent.textContent || '').trim();
                    if (parentText.includes('AI') && parentText.includes('手卡')) {
                        return true;
                    }
                    parent = parent.parentElement;
                    checkCount++;
                }
                
                return false;
            };
            
            // 方式1: 使用特定选择器，检查alt是否为"商品图"，且不是"AI手卡"图片
            image = item.querySelector(imageSelector);
            if (image && (isAIShoukaImage(image) || (image.alt || '').trim() !== '商品图')) {
                image = null;
            }
            
            // 方式2: 查找item中所有img，只选择alt为"商品图"的图片，排除"AI手卡"图片
            if (!image) {
                const images = Array.from(item.querySelectorAll("img"));
                image = images.find(img => {
                    const alt = (img.alt || '').trim();
                    const src = img.src || img.getAttribute('data-src') || '';
                    // 必须是"商品图"，且不是"AI手卡"图片
                    return src && src.trim() !== '' && 
                           alt === '商品图' && 
                           !isAIShoukaImage(img);
                });
            }
            
            return {
                imageUrl: image ? image.src : null,
                imageSrcset: image ? image.srcset : null,
                imageDataSrc: image ? image.getAttribute('data-src') : null,
                imageAlt: image ? (image.alt || '') : null,
                imageTitle: image ? (image.title || '') : null,
                imageSrc: image ? image.src : null,
                imageClassName: image ? image.className : null,
                imageParentText: image && image.parentElement ? (image.parentElement.textContent || '').substring(0, 100) : null
            };
        }
        """

    @staticmethod
    def click_explain_button() -> str:
        """点击"讲解"按钮的 JavaScript 代码。"""
        return """
        ({ itemSelector, buttonSelector, index }) => {
            const items = Array.from(document.querySelectorAll(itemSelector));
            const item = items[index];
            if (!item) {
                return { success: false, reason: 'Item not found' };
            }
            
            // 辅助函数：检查是否是下拉菜单的触发按钮
            const isDropdownTrigger = (node) => {
                const text = (node.textContent || '').trim();
                if (text === '...' || text === '⋯' || text === '⋮' || text.length <= 2) {
                    return true;
                }
                const className = node.className || '';
                if (typeof className === 'string') {
                    if (className.includes('dropdown') || className.includes('more') || 
                        className.includes('menu') || className.includes('trigger')) {
                        return true;
                    }
                }
                let parent = node.parentElement;
                let checkCount = 0;
                while (parent && checkCount < 3) {
                    const parentClass = parent.className || '';
                    if (typeof parentClass === 'string') {
                        if (parentClass.includes('dropdown') || parentClass.includes('menu')) {
                            return true;
                        }
                    }
                    parent = parent.parentElement;
                    checkCount++;
                }
                return false;
            };
            
            // 辅助函数：获取元素的完整文本
            const getFullText = (node) => {
                if (!node) return '';
                let text = (node.textContent || '').trim();
                if (!text) {
                    text = (node.innerText || '').trim();
                }
                if (!text) {
                    const innerSpan = node.querySelector('span');
                    if (innerSpan) {
                        text = (innerSpan.textContent || innerSpan.innerText || '').trim();
                    }
                }
                return text;
            };
            
            // 查找"讲解"按钮
            let button = null;
            
            // 方式1: 查找包含"讲解"文本的span，且类名包含selectBtn
            const selectBtnSpans = Array.from(item.querySelectorAll('span.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-selectBtn'));
            button = selectBtnSpans.find((span) => {
                const text = getFullText(span);
                return text === "讲解";
            });
            
            // 方式2: 如果没找到，查找包含"讲解"文本的span，但排除下拉菜单
            if (!button) {
                const allSpans = Array.from(item.querySelectorAll('span'));
                button = allSpans.find((span) => {
                    const text = getFullText(span);
                    return text === "讲解" && !isDropdownTrigger(span);
                });
            }
            
            // 方式3: 如果还是没找到，在整个item中查找
            if (!button) {
                const allButtons = Array.from(item.querySelectorAll('button, span, div, a'));
                button = allButtons.find((node) => {
                    const text = getFullText(node);
                    return text === "讲解" && !isDropdownTrigger(node);
                });
            }
            
            if (!button) {
                return { success: false, reason: 'Button not found' };
            }
            
            // 滚动到按钮位置
            button.scrollIntoView({ behavior: 'smooth', block: 'center' });
            
            // 等待一下，确保滚动完成
            setTimeout(() => {}, 100);
            
            // 尝试点击
            try {
                button.click();
                return { success: true };
            } catch (e) {
                // 如果直接点击失败，尝试触发事件
                try {
                    const event = new MouseEvent('click', {
                        bubbles: true,
                        cancelable: true,
                        view: window
                    });
                    button.dispatchEvent(event);
                    return { success: true };
                } catch (e2) {
                    return { success: false, reason: String(e2) };
                }
            }
        }
        """

    @staticmethod
    def get_product_list() -> str:
        """获取商品列表的 JavaScript 代码。"""
        return """
        ({ itemSelector, buttonSelector }) => {
            const items = Array.from(document.querySelectorAll(itemSelector));
            const result = [];
            
            for (let i = 0; i < items.length; i++) {
                const item = items[i];
                
                // 查找"讲解"按钮
                const selectBtnSpans = Array.from(item.querySelectorAll('span.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-selectBtn'));
                let buttonText = '';
                const button = selectBtnSpans.find((span) => {
                    const text = (span.textContent || '').trim();
                    if (text === '讲解') {
                        buttonText = text;
                        return true;
                    }
                    return false;
                });
                
                if (!button) {
                    // 尝试其他方式查找
                    const allSpans = Array.from(item.querySelectorAll('span'));
                    const found = allSpans.find((span) => {
                        const text = (span.textContent || '').trim();
                        if (text === '讲解') {
                            buttonText = text;
                            return true;
                        }
                        return false;
                    });
                    if (found) {
                        result.push({
                            index: i,
                            buttonText: buttonText || '未找到',
                            hasButton: true
                        });
                    } else {
                        result.push({
                            index: i,
                            buttonText: '未找到',
                            hasButton: false
                        });
                    }
                } else {
                    result.push({
                        index: i,
                        buttonText: buttonText || '讲解',
                        hasButton: true
                    });
                }
            }
            
            return result;
        }
        """

