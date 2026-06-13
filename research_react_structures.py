#!/usr/bin/env python3
"""Research React project structures from real-world examples"""

from playwright.sync_api import sync_playwright
import time

def research_projects():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        # 设置更长的超时时间
        page.set_default_timeout(30000)
        
        projects = [
            # Bulletproof React - 知名的React架构指南
            ("Bulletproof React /stores", "https://github.com/alan2207/bulletproof-react/tree/master/src/stores"),
            ("Bulletproof React /features", "https://github.com/alan2207/bulletproof-react/tree/master/src/features"),
            # Plane - 现代项目管理工具的 store 目录
            ("Plane.so /store", "https://github.com/makeplane/plane/tree/master/web/store"),
            # Cal.com 的 lib
            ("Cal.com /lib", "https://github.com/calcom/cal.com/tree/main/apps/web/lib"),
            # Documenso app structure
            ("Documenso /app", "https://github.com/documenso/documenso/tree/main/apps/web/src/app"),
            # Excalidraw - 白板应用
            ("Excalidraw /store", "https://github.com/excalidraw/excalidraw/tree/master/packages/excalidraw/store"),
        ]
        
        results = []
        
        for name, url in projects:
            print(f"\n{'='*60}")
            print(f"Researching: {name}")
            print(f"URL: {url}")
            print('='*60)
            
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                time.sleep(3)
                
                # 尝试多种选择器
                selectors = [
                    'div[role="row"] a[aria-label]',
                    'div[role="gridcell"] a',
                    'a.Link--primary',
                    'div.react-directory-filename-column a'
                ]
                
                structure = []
                for selector in selectors:
                    try:
                        elements = page.locator(selector).all()
                        if elements:
                            for elem in elements[:40]:
                                try:
                                    text = elem.inner_text(timeout=1000)
                                    if text and text.strip() and text.strip() not in structure:
                                        structure.append(text.strip())
                                except:
                                    pass
                            if structure:
                                break
                    except:
                        continue
                
                if structure:
                    print("\n📁 Directory Structure:")
                    for item in structure:
                        print(f"  - {item}")
                    results.append({
                        'name': name,
                        'url': url,
                        'structure': structure
                    })
                else:
                    print("  ⚠️  No structure found")
                
                time.sleep(2)
                
            except Exception as e:
                print(f"  ❌ Error: {e}")
                continue
        
        browser.close()
        return results

if __name__ == "__main__":
    results = research_projects()
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for r in results:
        print(f"\n{r['name']}:")
        print(f"  Items found: {len(r['structure'])}")
        print(f"  URL: {r['url']}")
