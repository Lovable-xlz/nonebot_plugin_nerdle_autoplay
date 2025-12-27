# 独立实现
"""
Nerdle Game 自动点击器 - Edge浏览器Windows优化版本
使用 Selenium 模拟浏览器点击关闭按钮（可视化界面）
"""

import time
import json
import traceback
import os
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    NoSuchElementException,
    WebDriverException
)

def load_equations_from_file():
    """
    从同目录下的 dic-8.json 文件中读取所有等式
    """
    # 获取当前脚本所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, "dic-8.json")
        
    print(f"尝试从文件读取等式: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        equations = json.load(f)
        
    # 验证每个等式都是字符串
    valid_equations = []
    for eq in equations:
        if isinstance(eq, str) and len(eq) == 8:
            valid_equations.append(eq)
        else:
            print(f"警告: 跳过无效等式: {eq}")
        
    print(f"✓ 从文件读取了 {len(valid_equations)} 个合法等式")
    return valid_equations

def nerdle_feedback(answer: str, guess: str):
    result = []
    used = [False] * 8

    # correct
    for i in range(8):
        if guess[i] == answer[i]:
            result.append({"char": guess[i], "status": "correct"})
            used[i] = True
        else:
            result.append(None)

    # present / absent
    for i in range(8):
        if result[i] is not None:
            continue

        found = False
        for j in range(8):
            if not used[j] and guess[i] == answer[j]:
                used[j] = True
                found = True
                break

        result[i] = {
            "char": guess[i],
            "status": "present" if found else "absent"
        }

    return result

def suggest_next_guess(candidates, history):
    """
    选择下一个猜测的等式
    对于candidates内剩余的每个等式，将所有候选等式依次作为answer，
    当前等式作为guess传到nerdle_feedback里并获得若干个反馈，
    将每个等式获得的反馈去重后选择不同反馈数量最多的等式并返回
    """
    if not candidates:
        return None
    
    best_guess = None
    max_unique_feedbacks = 0
    
    for guess_candidate in candidates:
        # 存储当前guess_candidate的所有反馈
        all_feedbacks = []
        
        # 对于candidates中的每个等式作为answer
        for answer_candidate in candidates:
            # 计算反馈
            feedback = nerdle_feedback(answer_candidate, guess_candidate)
            # 将反馈转换为可哈希的元组形式以便去重
            feedback_tuple = tuple((item['char'], item['status']) for item in feedback)
            all_feedbacks.append(feedback_tuple)
        
        # 去重并计算不同反馈的数量
        unique_feedbacks = set(all_feedbacks)
        unique_count = len(unique_feedbacks)
        
        # 选择不同反馈数量最多的等式
        if unique_count > max_unique_feedbacks:
            max_unique_feedbacks = unique_count
            best_guess = guess_candidate
        # 如果数量相同，保持第一个找到的
    
    return best_guess if best_guess else candidates[0]

def safe_find_elements(driver, by, selector, retries=3):
    """安全地查找元素，处理stale element异常"""
    for attempt in range(retries):
        try:
            return driver.find_elements(by, selector)
        except StaleElementReferenceException:
            if attempt < retries - 1:
                time.sleep(0.3)  # 增加等待时间
                continue
            raise
    return []

def filter_candidates_by_feedback(candidates, guess, real_feedback):
    """
    只保留：在假设 candidate 是答案时，
    它对 guess 产生的反馈 == 实际反馈
    """
    filtered = []

    for cand in candidates:
        simulated = nerdle_feedback(cand, guess)

        ok = True
        for i in range(8):
            if simulated[i]["status"] != real_feedback[i]["status"]:
                ok = False
                break

        if ok:
            filtered.append(cand)

    return filtered

def click_nerdle_close_button():
    # 使用Edge浏览器选项 - Windows优化
    edge_options = Options()
    
    # Windows Edge特定设置
    edge_options.use_chromium = True  # 强制使用Chromium内核
    edge_options.add_argument('--start-maximized')
    edge_options.add_argument('--disable-blink-features=AutomationControlled')
    edge_options.add_argument('--no-sandbox')  # Windows有时需要这个
    edge_options.add_argument('--disable-dev-shm-usage')  # 限制/dev/shm使用
    edge_options.add_argument('--disable-gpu')  # Windows上有时需要禁用GPU加速
    edge_options.add_argument('--disable-extensions')  # 禁用扩展
    edge_options.add_argument('--disable-infobars')  # 禁用信息栏
    edge_options.add_argument('--disable-notifications')  # 禁用通知
    edge_options.add_argument('--disable-popup-blocking')  # 禁用弹窗阻止
    
    # 减少日志输出
    edge_options.add_argument('--log-level=3')
    edge_options.add_argument('--silent')
    
    # 实验性选项
    edge_options.add_experimental_option('excludeSwitches', [
        'enable-automation',
        'enable-logging'  # 禁用详细日志
    ])
    edge_options.add_experimental_option('useAutomationExtension', False)
    
    # 设置页面加载策略
    edge_options.page_load_strategy = 'normal'  # 改为normal确保完全加载
    
    # 添加用户代理，避免被检测为机器人
    edge_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0')
    
    driver = None
    
    try:
        print("正在启动Edge浏览器...")
        
        # 尝试不同的初始化方式
        try:
            # 方式1: 尝试使用默认路径
            driver = webdriver.Edge(options=edge_options)
        except WebDriverException:
            # 方式2: 尝试指定常见Edge驱动路径
            import os
            common_paths = [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedgedriver.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedgedriver.exe",
                os.path.expanduser(r"~\AppData\Local\Microsoft\Edge\Application\msedgedriver.exe"),
                r"C:\Windows\System32\msedgedriver.exe",
            ]
            
            for path in common_paths:
                if os.path.exists(path):
                    try:
                        from selenium.webdriver.edge.service import Service
                        service = Service(executable_path=path)
                        driver = webdriver.Edge(service=service, options=edge_options)
                        print(f"使用Edge驱动路径: {path}")
                        break
                    except:
                        continue
        
        if driver is None:
            print("无法启动Edge浏览器")
            return False
        
        print("✓ Edge浏览器已启动")
        
        target_url = "https://nerdlegame.com/"
        print(f"\n正在访问 {target_url} ...")
        
        try:
            driver.set_page_load_timeout(5)  # 设置页面加载超时
            driver.get(target_url)
        except TimeoutException:
            print("页面加载超时，但可能已部分加载，继续执行...")
        except Exception as e:
            print(f"访问页面失败: {e}")
            return False
        
        # 等待页面基本加载
        time.sleep(2)
        
        # 简化广告拦截脚本，避免兼容性问题
        print("优化页面加载...")
        ad_block_script = """
(function() {
    console.log('优化页面加载...');
    // 简化版本，仅阻止明显的广告API
    if (typeof window.googletag !== 'undefined') {
        window.googletag.cmd = [];
        window.googletag.pubads = function() {
            return { refresh: function() {}, display: function() {} };
        };
    }
})();
"""
        try:
            driver.execute_script(ad_block_script)
            time.sleep(1)
        except:
            print("脚本注入失败，继续执行...")
        
        # 关闭弹窗 - 使用更可靠的方法
        print("尝试关闭弹窗...")
        found = False
        
        # 尝试简单的关闭方法：按ESC键
        try:
            from selenium.webdriver.common.action_chains import ActionChains
            actions = ActionChains(driver)
            actions.send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5)
            print("尝试ESC键关闭")
        except:
            pass

        # 开始游戏
        print("\n加载候选等式...")
        all_candidates = load_equations_from_file()
        print(f"✓ 共加载 {len(all_candidates)} 个候选等式")
        
        candidates = all_candidates[:]
        history = []
        first_guess = "1+56/7=9"
        
        attempt = 0
        while attempt < 6:
            print(f"\n第 {attempt + 1}/6 次尝试")
            user_input = suggest_next_guess(candidates, history) if attempt > 0 else first_guess
            print(f"使用: {user_input}")
            
            # 键盘输入
            try:
                # 确保页面有焦点
                driver.execute_script("window.focus();")
                time.sleep(0.2)
                
                # 使用JavaScript输入作为备选
                try:
                    body = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.TAG_NAME, 'body'))
                    )
                    for char in user_input:
                        body.send_keys(char)
                        time.sleep(0.1)
                    body.send_keys(Keys.RETURN)
                    print(f"✓ 输入完成")
                except:
                    # 如果常规输入失败，尝试JavaScript
                    print("常规输入失败，尝试JavaScript输入...")
                    script = f"""
                    var event = new KeyboardEvent('keydown', {{key: '{user_input[0]}'}});
                    document.dispatchEvent(event);
                    """
                    for char in user_input:
                        driver.execute_script(f"document.activeElement.value += '{char}';")
                        time.sleep(0.1)
                    driver.execute_script("""
                    var e = new KeyboardEvent('keydown', {key: 'Enter', keyCode: 13});
                    document.dispatchEvent(e);
                    """)
            except Exception as e:
                print(f"✗ 输入失败: {e}")
                traceback.print_exc()
            
            # 等待结果显示
            time.sleep(1)
            
            # 读取最新一行的结果
            try:
                # 等待结果出现
                time.sleep(0.5)
                
                # 尝试多种方式查找行
                rows = []
                row_selectors = [
                    'div[id^="row"]',
                    'div[class*="row"]',
                    'div.row',
                    'div.game-row',
                    'div.guess-row'
                ]
                
                for selector in row_selectors:
                    try:
                        rows = safe_find_elements(driver, By.CSS_SELECTOR, selector)
                        if rows:
                            break
                    except:
                        continue
                
                if len(rows) >= attempt + 1:
                    # 重新获取当前行元素
                    current_row = rows[attempt]
                    
                    # 尝试多种方式查找单元格
                    cells = []
                    cell_selectors = [
                        'div.keyboard-cell',
                        'div.tile',
                        'div[class*="cell"]',
                        'div[class*="tile"]',
                        'div.guess-cell'
                    ]
                    
                    for selector in cell_selectors:
                        try:
                            cells = safe_find_elements(current_row, By.CSS_SELECTOR, selector)
                            if cells and len(cells) >= 8:
                                break
                        except:
                            continue
                    
                    result = []
                    if cells:
                        cell_index = 0
                        while cell_index < len(cells):
                            try:
                                # 尝试多种方式获取状态
                                cell = cells[cell_index]
                                
                                # 方法1: aria-label属性
                                aria_label = cell.get_attribute('aria-label')
                                if aria_label and aria_label.strip():
                                    parts = aria_label.strip().split()
                                    if len(parts) >= 2:
                                        char = parts[0]
                                        status = parts[1].lower()
                                        result.append({"char": char, "status": status})
                                        cell_index += 1
                                        continue
                                
                                # 方法2: class名称
                                classes = cell.get_attribute('class')
                                if classes:
                                    if 'correct' in classes:
                                        char = user_input[cell_index] if cell_index < len(user_input) else '?'
                                        result.append({"char": char, "status": "correct"})
                                    elif 'present' in classes or 'wrong-place' in classes:
                                        char = user_input[cell_index] if cell_index < len(user_input) else '?'
                                        result.append({"char": char, "status": "present"})
                                    elif 'absent' in classes or 'wrong' in classes:
                                        char = user_input[cell_index] if cell_index < len(user_input) else '?'
                                        result.append({"char": char, "status": "absent"})
                                    else:
                                        # 默认状态
                                        result.append({"char": user_input[cell_index] if cell_index < len(user_input) else '?', "status": "absent"})
                                
                                cell_index += 1
                            except StaleElementReferenceException:
                                # 元素失效，重新获取
                                rows = safe_find_elements(driver, By.CSS_SELECTOR, 'div[id^="row"]')
                                if len(rows) > attempt:
                                    current_row = rows[attempt]
                                    cells = safe_find_elements(current_row, By.CSS_SELECTOR, 'div.keyboard-cell')
                                else:
                                    break
                            except IndexError:
                                break
                    
                    # 如果无法获取结果，使用模拟反馈
                    if not result and user_input:
                        print("无法读取结果，使用模拟反馈...")
                        # 这里应该根据实际情况调整，暂时使用简单模拟
                        for i in range(8):
                            result.append({"char": user_input[i], "status": "absent"})
                    
                    if result:
                        print(f"结果: {json.dumps(result, ensure_ascii=False)}")
                        
                        # 检查是否全部正确
                        if all(fb.get('status') == 'correct' for fb in result):
                            print(f"🎉 正确！")
                            input("按Enter键继续...")
                            break
                        
                        # 过滤候选
                        history.append({"guess": user_input, "feedback": result})
                        candidates = all_candidates[:]
                        for h in history:
                            candidates = filter_candidates_by_feedback(
                                candidates, h['guess'], h['feedback']
                            )
                        
                        print(f"剩余: {len(candidates)} 个")
                        if len(candidates) > 0:
                            print(f"💡 {suggest_next_guess(candidates, history)}")
                            if len(candidates) <= 10:
                                print(f"全部: {', '.join(candidates)}")
                        else:
                            print(f"⚠️ 无候选")
                    else:
                        print("无法获取结果")
                
                else:
                    print(f"✗ 未找到第 {attempt + 1} 行")
            except Exception as e:
                print(f"✗ 读取结果失败: {e}")
                traceback.print_exc()
            
            attempt += 1
        
        return found
        
    except Exception as e:
        print(f"\n程序运行错误: {e}")
        traceback.print_exc()
        return False
        
    finally:
        if driver:
            try:
                driver.quit()
                print("Edge浏览器已关闭")
            except:
                print("关闭浏览器时出错")


if __name__ == "__main__":
    # 运行主函数
    success = click_nerdle_close_button()
    
    print("\n✓ 程序执行完毕")
        
    # 防止窗口立即关闭
    input("\n按Enter键退出程序...")
