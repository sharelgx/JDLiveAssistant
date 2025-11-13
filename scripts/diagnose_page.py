#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
页面诊断脚本
用于分析京东直播后台页面结构，找出为什么无法定位商品元素
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from playwright.sync_api import sync_playwright


def diagnose_page(port: int = 9222):
    """诊断页面结构"""
    print("=" * 80)
    print("京东直播后台页面诊断工具")
    print("=" * 80)
    print()
    
    with sync_playwright() as p:
        try:
            print(f"正在连接到浏览器调试端口 {port}...")
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            print("✓ 浏览器连接成功")
            
            # 获取所有上下文
            contexts = browser.contexts
            print(f"✓ 找到 {len(contexts)} 个浏览器上下文")
            
            if not contexts:
                print("✗ 错误: 没有找到浏览器上下文")
                return
            
            # 收集所有页面
            all_pages = []
            for ctx_idx, context in enumerate(contexts):
                pages = context.pages
                for page in pages:
                    try:
                        page_title = page.title()
                    except:
                        page_title = "(无标题)"
                    all_pages.append({
                        'context_index': ctx_idx,
                        'page': page,
                        'url': page.url,
                        'title': page_title
                    })
            
            print(f"✓ 总共找到 {len(all_pages)} 个页面")
            print()
            
            if not all_pages:
                print("✗ 错误: 没有找到页面")
                return
            
            # 列出所有页面
            print("=" * 80)
            print("浏览器中打开的所有页面：")
            print("=" * 80)
            for idx, page_info in enumerate(all_pages):
                url = page_info['url']
                title = page_info['title']
                # 判断是否可能是京东直播后台页面
                is_jd = 'jd.com' in url.lower() or '京东' in title or '直播' in title or '商品' in title
                marker = " ★★★ (可能是目标页面)" if is_jd else ""
                print(f"\n[{idx}] {title}{marker}")
                print(f"    URL: {url[:100]}")
                if len(url) > 100:
                    print(f"         {url[100:][:100]}")
            
            print()
            print("=" * 80)
            
            # 自动选择最可能的页面或让用户选择
            target_page_info = None
            
            # 优先选择京东相关页面
            jd_pages = [p for p in all_pages if 'jd.com' in p['url'].lower() or '京东' in p['title'] or '直播' in p['title']]
            if len(jd_pages) == 1:
                target_page_info = jd_pages[0]
                print(f"✓ 自动选择京东相关页面: [{all_pages.index(target_page_info)}] {target_page_info['title']}")
            elif len(jd_pages) > 1:
                print(f"找到 {len(jd_pages)} 个京东相关页面，请选择要诊断的页面：")
                for jd_page in jd_pages:
                    idx = all_pages.index(jd_page)
                    print(f"  [{idx}] {jd_page['title']}")
                print()
                try:
                    choice = input(f"请输入页面编号 (0-{len(all_pages)-1}，直接回车选择第一个京东页面): ").strip()
                    if choice == "":
                        target_page_info = jd_pages[0]
                    else:
                        choice_idx = int(choice)
                        if 0 <= choice_idx < len(all_pages):
                            target_page_info = all_pages[choice_idx]
                        else:
                            print(f"无效的选择，使用第一个京东页面")
                            target_page_info = jd_pages[0]
                except (ValueError, KeyboardInterrupt):
                    print("使用第一个京东页面")
                    target_page_info = jd_pages[0]
            else:
                # 没有找到京东页面，让用户选择
                print("未找到京东相关页面，请选择要诊断的页面：")
                try:
                    choice = input(f"请输入页面编号 (0-{len(all_pages)-1}，直接回车使用第一个页面): ").strip()
                    if choice == "":
                        target_page_info = all_pages[0]
                    else:
                        choice_idx = int(choice)
                        if 0 <= choice_idx < len(all_pages):
                            target_page_info = all_pages[choice_idx]
                        else:
                            print(f"无效的选择，使用第一个页面")
                            target_page_info = all_pages[0]
                except (ValueError, KeyboardInterrupt):
                    print("使用第一个页面")
                    target_page_info = all_pages[0]
            
            page = target_page_info['page']
            print()
            print("=" * 80)
            print(f"正在诊断页面: {target_page_info['title']}")
            print(f"URL: {page.url}")
            print("=" * 80)
            print()
            
            # 执行诊断脚本
            print("=" * 80)
            print("开始执行页面诊断...")
            print("=" * 80)
            print()
            
            result = page.evaluate("""
                () => {
                    // 1. 基本页面信息
                    const basicInfo = {
                        url: window.location.href,
                        title: document.title,
                        readyState: document.readyState,
                        hasBody: !!document.body,
                        bodyChildren: document.body ? document.body.children.length : 0,
                        bodyHtmlLength: document.body ? document.body.innerHTML.length : 0
                    };
                    
                    // 2. 框架信息
                    const iframes = document.querySelectorAll('iframe');
                    const frameInfo = {
                        count: iframes.length,
                        frames: Array.from(iframes).slice(0, 5).map((iframe, idx) => ({
                            index: idx,
                            src: iframe.src || '',
                            id: iframe.id || '',
                            name: iframe.name || ''
                        }))
                    };
                    
                    // 3. 表格相关元素
                    const tables = document.querySelectorAll('table');
                    const antTables = document.querySelectorAll('table.ant-table, .ant-table');
                    const tbodies = document.querySelectorAll('tbody');
                    const antTableTbodies = document.querySelectorAll('tbody.ant-table-tbody');
                    const allTrs = document.querySelectorAll('tr');
                    const antTableRows = document.querySelectorAll('tr.ant-table-row');
                    
                    const tableInfo = {
                        totalTables: tables.length,
                        antTables: antTables.length,
                        totalTbodies: tbodies.length,
                        antTableTbodies: antTableTbodies.length,
                        totalTrs: allTrs.length,
                        antTableRows: antTableRows.length
                    };
                    
                    // 4. 商品容器相关元素
                    const skuContainers = document.querySelectorAll('div.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-skuContainer');
                    const oldWrappers = document.querySelectorAll('div.antd-pro-pages-control-panel-goods-components-normal-goods-sku-item-index-wrapper');
                    const goodsElements = document.querySelectorAll('[class*="goods"]');
                    const skuElements = document.querySelectorAll('[class*="sku"]');
                    
                    const containerInfo = {
                        skuContainers: skuContainers.length,
                        oldWrappers: oldWrappers.length,
                        goodsElements: goodsElements.length,
                        skuElements: skuElements.length
                    };
                    
                    // 5. "讲解"按钮相关信息
                    const allButtons = document.querySelectorAll('button, a, span, div');
                    const explainButtons = Array.from(allButtons).filter(el => {
                        const text = (el.textContent || '').trim();
                        return text === '讲解' || text.includes('讲解');
                    });
                    
                    const buttonInfo = {
                        totalButtons: allButtons.length,
                        explainButtonCount: explainButtons.length,
                        explainButtonDetails: explainButtons.slice(0, 10).map((btn, idx) => {
                            const rect = btn.getBoundingClientRect();
                            return {
                                index: idx,
                                tag: btn.tagName,
                                text: (btn.textContent || '').trim().substring(0, 50),
                                className: (btn.className || '').toString().substring(0, 100),
                                visible: rect.width > 0 && rect.height > 0,
                                top: Math.round(rect.top),
                                left: Math.round(rect.left)
                            };
                        })
                    };
                    
                    // 6. 找出"讲解"按钮的父容器层级结构
                    const containerHierarchy = [];
                    explainButtons.slice(0, 3).forEach((btn, btnIdx) => {
                        const hierarchy = [];
                        let parent = btn.parentElement;
                        let depth = 0;
                        
                        while (parent && depth < 15) {
                            const className = parent.className || '';
                            const classStr = typeof className === 'string' ? className : className.toString();
                            hierarchy.push({
                                depth: depth,
                                tag: parent.tagName,
                                className: classStr.substring(0, 100),
                                id: parent.id || ''
                            });
                            parent = parent.parentElement;
                            depth++;
                        }
                        
                        containerHierarchy.push({
                            buttonIndex: btnIdx,
                            hierarchy: hierarchy
                        });
                    });
                    
                    // 7. 获取第一个TR的完整HTML（如果存在）
                    let firstTrHtml = '';
                    if (antTableRows.length > 0) {
                        firstTrHtml = antTableRows[0].outerHTML.substring(0, 1000);
                    } else if (allTrs.length > 0) {
                        firstTrHtml = allTrs[0].outerHTML.substring(0, 1000);
                    }
                    
                    // 8. 加载状态检查
                    const loadingElements = document.querySelectorAll('.ant-spin-spinning, .page-loading-warp, [class*="loading"], [class*="spin"]');
                    const loadingInfo = {
                        hasLoading: loadingElements.length > 0,
                        loadingCount: loadingElements.length
                    };
                    
                    // 9. React相关
                    const reactRoots = document.querySelectorAll('[id*="root"], [id*="app"], [class*="root"], [class*="app"]');
                    const reactInfo = {
                        reactRootCount: reactRoots.length
                    };
                    
                    return {
                        basicInfo,
                        frameInfo,
                        tableInfo,
                        containerInfo,
                        buttonInfo,
                        containerHierarchy,
                        firstTrHtml,
                        loadingInfo,
                        reactInfo
                    };
                }
            """)
            
            # 打印诊断结果
            print("【基本页面信息】")
            print(f"  页面标题(Python): {target_page_info['title']}")
            print(f"  URL: {result['basicInfo']['url']}")
            print(f"  页面标题(JS): {result['basicInfo']['title']}")
            print(f"  readyState: {result['basicInfo']['readyState']}")
            print(f"  是否有body: {result['basicInfo']['hasBody']}")
            print(f"  body子元素数量: {result['basicInfo']['bodyChildren']}")
            print(f"  body HTML长度: {result['basicInfo']['bodyHtmlLength']} 字符")
            print()
            
            print("【框架信息】")
            print(f"  iframe数量: {result['frameInfo']['count']}")
            for frame in result['frameInfo']['frames']:
                print(f"  - iframe {frame['index']}: src={frame['src'][:80] if frame['src'] else '(空)'}, id={frame['id']}, name={frame['name']}")
            print()
            
            print("【表格相关元素】")
            print(f"  总表格数: {result['tableInfo']['totalTables']}")
            print(f"  Ant Design表格数: {result['tableInfo']['antTables']}")
            print(f"  总tbody数: {result['tableInfo']['totalTbodies']}")
            print(f"  Ant Design tbody数: {result['tableInfo']['antTableTbodies']}")
            print(f"  总tr元素数: {result['tableInfo']['totalTrs']}")
            print(f"  ★ tr.ant-table-row数: {result['tableInfo']['antTableRows']}")
            print()
            
            print("【商品容器相关元素】")
            print(f"  skuContainer数量: {result['containerInfo']['skuContainers']}")
            print(f"  旧wrapper数量: {result['containerInfo']['oldWrappers']}")
            print(f"  包含'goods'的元素: {result['containerInfo']['goodsElements']}")
            print(f"  包含'sku'的元素: {result['containerInfo']['skuElements']}")
            print()
            
            print("【'讲解'按钮信息】")
            print(f"  总按钮数量: {result['buttonInfo']['totalButtons']}")
            print(f"  ★ '讲解'按钮数量: {result['buttonInfo']['explainButtonCount']}")
            if result['buttonInfo']['explainButtonDetails']:
                print(f"\n  前 {len(result['buttonInfo']['explainButtonDetails'])} 个'讲解'按钮详情:")
                for btn in result['buttonInfo']['explainButtonDetails']:
                    visible_str = "可见" if btn['visible'] else "不可见"
                    print(f"    按钮{btn['index']+1}: <{btn['tag']}> 文本='{btn['text']}'")
                    print(f"             类名={btn['className'][:60]}")
                    print(f"             状态={visible_str}, 位置=({btn['left']}, {btn['top']})")
            print()
            
            print("【'讲解'按钮的父容器层级结构】")
            for container in result['containerHierarchy']:
                print(f"\n  按钮 {container['buttonIndex']+1} 的父容器层级:")
                for level in container['hierarchy'][:10]:  # 只显示前10层
                    indent = "  " * (level['depth'] + 2)
                    id_str = f" id='{level['id']}'" if level['id'] else ""
                    class_str = level['className'][:50] if level['className'] else "(无类名)"
                    print(f"{indent}↑ <{level['tag']}>{id_str} class='{class_str}'")
            print()
            
            print("【加载状态】")
            print(f"  是否有加载动画: {result['loadingInfo']['hasLoading']}")
            print(f"  加载动画数量: {result['loadingInfo']['loadingCount']}")
            print()
            
            print("【React信息】")
            print(f"  React根元素数量: {result['reactInfo']['reactRootCount']}")
            print()
            
            if result['firstTrHtml']:
                print("【第一个TR的HTML片段】")
                print(result['firstTrHtml'])
                print()
            
            # 保存完整结果到JSON文件
            output_file = project_root / "scripts" / "page_diagnosis_result.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"完整诊断结果已保存到: {output_file}")
            print()
            
            # 给出诊断建议
            print("=" * 80)
            print("【诊断建议】")
            print("=" * 80)
            
            if result['buttonInfo']['explainButtonCount'] == 0:
                print("❌ 问题: 页面上没有找到'讲解'按钮")
                print("   建议:")
                print("   1. 确认浏览器是否打开了京东直播后台商品管理页面")
                print("   2. 检查页面是否完全加载")
                print("   3. 尝试刷新页面")
            elif result['tableInfo']['antTableRows'] == 0:
                print("❌ 问题: 找到了'讲解'按钮，但没有找到tr.ant-table-row元素")
                print("   建议:")
                print("   1. 页面结构可能已改变，需要更新选择器")
                print("   2. 查看上面的'讲解按钮的父容器层级结构'，找到正确的商品容器")
            else:
                print("✓ 页面元素检测正常")
                print(f"  - 找到 {result['tableInfo']['antTableRows']} 个商品行")
                print(f"  - 找到 {result['buttonInfo']['explainButtonCount']} 个'讲解'按钮")
            
            print()
            
        except Exception as e:
            print(f"✗ 错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            try:
                browser.close()
            except:
                pass


if __name__ == "__main__":
    print()
    port = 9222
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"警告: 无效的端口号 '{sys.argv[1]}'，使用默认端口 9222")
    
    diagnose_page(port)

