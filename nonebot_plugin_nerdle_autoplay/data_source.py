# 渲染部分基本同 nonebot_plugin_nerdle 的 data_source.py，AutoPlayer 部分由 click_nerdle.py 重构而来
from enum import Enum
from io import BytesIO
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
import time
import json
import traceback
import os

from PIL import Image, ImageDraw, ImageFont
from PIL.Image import Image as IMG
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException,
    NoSuchElementException,
    WebDriverException
)

# 常量定义
BLOCK_SIZE = (40, 40)
BLOCK_PADDING = (10, 10)
PADDING = (20, 20)
BORDER_WIDTH = 2
FONT_SIZE = 20

# 颜色定义
CORRECT_COLOR = (134, 163, 115)  # 绿色
EXIST_COLOR = (198, 182, 109)    # 黄色
WRONG_COLOR = (123, 123, 124)    # 灰色
BORDER_COLOR = (123, 123, 124)   # 边框颜色
BG_COLOR = (255, 255, 255)       # 背景颜色
FONT_COLOR = (255, 255, 255)     # 文字颜色
UNGUESSED_COLOR = (255, 255, 255)  # 未猜测字符的背景颜色（白色）
UNGUESSED_FONT_COLOR = (123, 123, 124)  # 未猜测字符的字体颜色（灰色）

@dataclass
class GameStep:
    """游戏步骤"""
    guess: str
    feedback: List[Dict[str, str]]  # 每个字符的反馈
    candidate_count: int  # 剩余候选数量
    next_suggestion: str  # 下一个建议
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "guess": self.guess,
            "feedback": self.feedback,
            "candidate_count": self.candidate_count,
            "next_suggestion": self.next_suggestion
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GameStep':
        return cls(
            guess=data["guess"],
            feedback=data["feedback"],
            candidate_count=data["candidate_count"],
            next_suggestion=data["next_suggestion"]
        )


@dataclass
class GameHistory:
    """游戏历史记录"""
    answer: str
    steps: List[GameStep] = field(default_factory=list)
    date: str = ""
    cached_time: str = ""  # 新增：缓存时间（精确到分钟）
    
    def __post_init__(self):
        self.step_char_status_history = []  # 记录每一步的字符状态历史
        # 如果没有设置缓存时间，使用当前时间
        if not self.cached_time:
            self.cached_time = time.strftime("%Y-%m-%d %H:%M")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "steps": [step.to_dict() for step in self.steps],
            "date": self.date or time.strftime("%Y-%m-%d"),
            "cached_time": self.cached_time  # 保存缓存时间
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GameHistory':
        history = cls(
            answer=data["answer"],
            steps=[GameStep.from_dict(step) for step in data["steps"]],
            date=data.get("date", "")
        )
        # 设置缓存时间
        history.cached_time = data.get("cached_time", time.strftime("%Y-%m-%d %H:%M"))
        return history
    
    def get_char_status_at_step(self, step_index: int) -> Dict[str, str]:
        """获取在特定步骤时的字符状态"""
        all_chars = "0123456789+-*/="
        char_status = {}
        
        # 初始状态：所有字符都为unguessed
        for char in all_chars:
            char_status[char] = "unguessed"
        
        # 遍历到指定步骤，更新字符状态
        for i in range(step_index + 1):
            if i >= len(self.steps):
                break
                
            step = self.steps[i]
            guess = step.guess
            feedback = step.feedback
            
            # 计算这次猜测中每个字符的状态
            guess_status = {}
            for j, char in enumerate(guess):
                fb = feedback[j]
                guess_status[char] = fb["status"]
            
            # 根据状态优先级更新字符状态
            # 优先级：correct > present > absent > unguessed
            for char, new_status in guess_status.items():
                current_status = char_status.get(char, "unguessed")
                
                status_priority = {
                    "unguessed": 0,
                    "absent": 1,
                    "present": 2,
                    "correct": 3
                }
                
                # 如果新状态优先级更高，则更新
                new_priority = status_priority.get(new_status, 0)
                current_priority = status_priority.get(current_status, 0)
                
                if new_priority > current_priority:
                    # 转换状态名称以匹配渲染逻辑
                    if new_status == "absent":
                        char_status[char] = "wrong"
                    elif new_status == "present":
                        char_status[char] = "exist"
                    elif new_status == "correct":
                        char_status[char] = "correct"
        
        return char_status
    
    def draw_block(self, color: tuple[int, int, int], char: str, 
                   font: ImageFont.FreeTypeFont, font_color: tuple[int, int, int] = None) -> IMG:
        """绘制单个方块"""
        block = Image.new("RGB", BLOCK_SIZE, BORDER_COLOR)
        inner_w = BLOCK_SIZE[0] - BORDER_WIDTH * 2
        inner_h = BLOCK_SIZE[1] - BORDER_WIDTH * 2
        inner = Image.new("RGB", (inner_w, inner_h), color)
        block.paste(inner, (BORDER_WIDTH, BORDER_WIDTH))
        if char:
            draw = ImageDraw.Draw(block)
            bbox = font.getbbox(char)
            x = (BLOCK_SIZE[0] - bbox[2]) / 2
            y = (BLOCK_SIZE[1] - bbox[3]) / 2
            
            # 使用指定的字体颜色，如果没有指定则使用默认的字体颜色
            text_color = font_color if font_color is not None else FONT_COLOR
            draw.text((x, y), char, font=font, fill=text_color)
        return block
    
    def render_step_image(self, step_index: int) -> BytesIO:
        """渲染指定步骤时的图片（显示到该步骤为止的所有猜测）"""
        if not self.steps or step_index < 0:
            return self.render_final_image()
        
        length = len(self.answer)
        rows = length - 2  # 最大猜测次数
        
        # 计算主游戏区域宽度
        main_board_w = length * BLOCK_SIZE[0]
        main_board_w += (length - 1) * BLOCK_PADDING[0] + 2 * PADDING[0]
        
        # 计算字符状态区域宽度
        char_blocks_per_row = 5  # 每行5个字符
        char_board_w = char_blocks_per_row * BLOCK_SIZE[0]
        char_board_w += (char_blocks_per_row - 1) * BLOCK_PADDING[0] + 2 * PADDING[0]
        
        # 画布宽度取两者较大值
        board_w = max(main_board_w, char_board_w)
        
        # 计算主游戏区域高度
        main_board_h = rows * BLOCK_SIZE[1]
        main_board_h += (rows - 1) * BLOCK_PADDING[1] + 2 * PADDING[1]
        
        # 计算字符状态区域高度（3行）
        char_status_rows = 3
        char_status_h = char_status_rows * BLOCK_SIZE[1]
        char_status_h += (char_status_rows - 1) * BLOCK_PADDING[1] + 2 * PADDING[1]
        
        # 总高度 = 主游戏区域高度 + 字符状态区域高度
        total_h = main_board_h + char_status_h
        
        # 创建画布
        board_size = (board_w, total_h)
        board = Image.new("RGB", board_size, BG_COLOR)
        
        # 加载字体
        try:
            font_path = os.path.join(os.path.dirname(__file__), "resources", "fonts", "KarnakPro-Bold.ttf")
            font = ImageFont.truetype(font_path, FONT_SIZE, encoding="utf-8")
        except:
            font = ImageFont.load_default()
        
        # 计算主游戏区域的起始X坐标，使其居中
        main_board_start_x = (board_w - main_board_w) // 2 + PADDING[0]
        
        # 获取该步骤时的字符状态
        char_status = self.get_char_status_at_step(step_index)
        
        # 绘制主游戏区域（显示到当前步骤为止的所有猜测）
        for row in range(rows):
            if row <= step_index and row < len(self.steps):
                guessed_equation = self.steps[row].guess
                feedback = self.steps[row].feedback
                
                blocks: list[IMG] = []
                for i in range(length):
                    char = guessed_equation[i]
                    fb = feedback[i]
                    
                    # 根据反馈选择颜色
                    if fb["status"] == "correct":
                        color = CORRECT_COLOR
                    elif fb["status"] == "present":
                        color = EXIST_COLOR
                    else:
                        color = WRONG_COLOR
                    
                    blocks.append(self.draw_block(color, char, font))
            else:
                blocks = [self.draw_block(BG_COLOR, "", font) for _ in range(length)]
            
            # 放置方块
            for col, block in enumerate(blocks):
                x = main_board_start_x + (BLOCK_SIZE[0] + BLOCK_PADDING[0]) * col
                y = PADDING[1] + (BLOCK_SIZE[1] + BLOCK_PADDING[1]) * row
                board.paste(block, (int(x), int(y)))
        
        # 绘制字符状态区域
        chars = "0123456789+-*/="  # 15个字符
        char_blocks_per_row = 5  # 每行5个字符
        
        # 计算字符状态区域的起始Y坐标
        char_start_y = main_board_h + PADDING[1]
        
        # 计算字符状态区域的起始X坐标，使其居中
        char_board_content_w = char_blocks_per_row * BLOCK_SIZE[0]
        char_board_content_w += (char_blocks_per_row - 1) * BLOCK_PADDING[0]
        char_start_x = (board_w - char_board_content_w) // 2
        
        for row in range(char_status_rows):
            for col in range(char_blocks_per_row):
                char_index = row * char_blocks_per_row + col
                if char_index < len(chars):
                    char = chars[char_index]
                    # 根据字符状态选择颜色
                    status = char_status.get(char, "unguessed")
                    if status == "correct":
                        color = CORRECT_COLOR
                        font_color = FONT_COLOR  # 白色字体
                    elif status == "exist":
                        color = EXIST_COLOR
                        font_color = FONT_COLOR  # 白色字体
                    elif status == "wrong":
                        color = WRONG_COLOR
                        font_color = FONT_COLOR  # 白色字体
                    else:  # unguessed
                        color = UNGUESSED_COLOR  # 白色背景
                        font_color = UNGUESSED_FONT_COLOR  # 灰色字体
                    
                    # 绘制字符块
                    block = self.draw_block(color, char, font, font_color)
                    x = char_start_x + (BLOCK_SIZE[0] + BLOCK_PADDING[0]) * col
                    y = char_start_y + (BLOCK_SIZE[1] + BLOCK_PADDING[1]) * row
                    board.paste(block, (int(x), int(y)))
        
        # 保存为BytesIO
        output = BytesIO()
        board = board.convert("RGBA")
        board.save(output, format="png")
        output.seek(0)
        return output
    
    def render_final_image(self) -> BytesIO:
        """渲染最终结果图片（显示所有猜测）"""
        if not self.steps:
            # 返回空图片
            output = BytesIO()
            img = Image.new("RGB", (100, 100), BG_COLOR)
            img.save(output, format="png")
            output.seek(0)
            return output
        
        # 渲染最后一步的图片
        return self.render_step_image(len(self.steps) - 1)


class NerdleAutoPlayer:
    """Nerdle自动玩家 - 基于可运行代码重构"""
    
    def __init__(self):
        self.driver = None
        self.all_candidates = []
        self.load_equations()
    
    def load_equations(self):
        """从文件加载等式"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(current_dir, "resources", "equals", "dic-8.json")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                equations = json.load(f)
            
            valid_equations = []
            for eq in equations:
                if isinstance(eq, str) and len(eq) == 8:
                    valid_equations.append(eq)
                else:
                    print(f"警告: 跳过无效等式: {eq}")
            
            self.all_candidates = valid_equations
            print(f"✓ 从文件读取了 {len(self.all_candidates)} 个合法等式")
        except Exception as e:
            print(f"✗ 加载等式失败: {e}")
            self.all_candidates = []
    
    def nerdle_feedback(self, answer: str, guess: str):
        """计算反馈"""
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
    
    def suggest_next_guess(self, candidates, history):
        """建议下一个猜测"""
        if not candidates:
            return None
        
        best_guess = None
        max_unique_feedbacks = 0
        
        for guess_candidate in candidates:
            all_feedbacks = []
            
            for answer_candidate in candidates:
                feedback = self.nerdle_feedback(answer_candidate, guess_candidate)
                feedback_tuple = tuple((item['char'], item['status']) for item in feedback)
                all_feedbacks.append(feedback_tuple)
            
            unique_feedbacks = set(all_feedbacks)
            unique_count = len(unique_feedbacks)
            
            if unique_count > max_unique_feedbacks:
                max_unique_feedbacks = unique_count
                best_guess = guess_candidate
        
        return best_guess if best_guess else candidates[0]
    
    def filter_candidates_by_feedback(self, candidates, guess, real_feedback):
        """根据反馈过滤候选"""
        filtered = []
        
        for cand in candidates:
            simulated = self.nerdle_feedback(cand, guess)
            
            ok = True
            for i in range(8):
                if simulated[i]["status"] != real_feedback[i]["status"]:
                    ok = False
                    break
            
            if ok:
                filtered.append(cand)
        
        return filtered
    
    def safe_find_elements(self, by, selector, retries=3):
        """安全地查找元素"""
        for attempt in range(retries):
            try:
                return self.driver.find_elements(by, selector)
            except StaleElementReferenceException:
                if attempt < retries - 1:
                    time.sleep(0.3)
                    continue
                raise
        return []
    
    def setup_driver(self):
        """设置浏览器驱动 - Windows Edge优化版本"""
        edge_options = Options()
        
        # Windows Edge特定设置
        edge_options.use_chromium = True
        edge_options.add_argument('--start-maximized')
        edge_options.add_argument('--disable-blink-features=AutomationControlled')
        edge_options.add_argument('--no-sandbox')
        edge_options.add_argument('--disable-dev-shm-usage')
        edge_options.add_argument('--disable-gpu')
        edge_options.add_argument('--disable-extensions')
        edge_options.add_argument('--disable-infobars')
        edge_options.add_argument('--disable-notifications')
        edge_options.add_argument('--disable-popup-blocking')
        edge_options.add_argument('--log-level=3')
        edge_options.add_argument('--silent')
        
        # 实验性选项
        edge_options.add_experimental_option('excludeSwitches', [
            'enable-automation',
            'enable-logging'
        ])
        edge_options.add_experimental_option('useAutomationExtension', False)
        
        # 设置页面加载策略
        edge_options.page_load_strategy = 'normal'
        
        # 添加用户代理
        edge_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0')
        
        # 尝试启动浏览器
        try:
            driver = webdriver.Edge(options=edge_options)
            self.driver = driver
            print("✓ Edge浏览器已启动")
            return True
        except WebDriverException:
            # 尝试指定常见Edge驱动路径
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
                        self.driver = driver
                        print(f"✓ Edge浏览器已启动（使用驱动路径: {path}）")
                        return True
                    except:
                        continue
            
            print("✗ 无法启动Edge浏览器")
            return False
        except Exception as e:
            print(f"✗ 启动浏览器失败: {e}")
            return False
    
    def get_feedback_from_page(self, attempt: int, user_input: str):
        """从页面获取反馈 - 简化稳定版本"""
        try:
            # 等待结果显示
            time.sleep(1.5)
            
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
                    rows = self.safe_find_elements(By.CSS_SELECTOR, selector)
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
                        cells = current_row.find_elements(By.CSS_SELECTOR, selector)
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
                                    result.append({
                                        "char": user_input[cell_index] if cell_index < len(user_input) else '?', 
                                        "status": "absent"
                                    })
                            
                            cell_index += 1
                        except StaleElementReferenceException:
                            # 元素失效，重新获取
                            rows = self.safe_find_elements(By.CSS_SELECTOR, 'div[id^="row"]')
                            if len(rows) > attempt:
                                current_row = rows[attempt]
                                cells = current_row.find_elements(By.CSS_SELECTOR, 'div.keyboard-cell')
                            else:
                                break
                        except IndexError:
                            break
                
                # 如果无法获取结果，使用模拟反馈
                if not result and user_input:
                    print("无法读取结果，使用模拟反馈...")
                    # 使用简单模拟
                    for i in range(8):
                        result.append({"char": user_input[i], "status": "absent"})
                
                return result[:8]  # 确保只返回8个
            else:
                print(f"✗ 未找到第 {attempt + 1} 行")
                return None
                
        except Exception as e:
            print(f"✗ 读取结果失败: {e}")
            return None
    
    def optimize_page_loading(self):
        """优化页面加载"""
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
            self.driver.execute_script(ad_block_script)
            time.sleep(1)
        except:
            print("脚本注入失败，继续执行...")
    
    def run_auto_game(self) -> GameHistory | None:
        """运行自动游戏 - 主逻辑"""
        if not self.setup_driver():
            return None
        
        try:
            # 访问网站
            print("访问 nerdlegame.com...")
            target_url = "https://nerdlegame.com/"
            
            try:
                self.driver.set_page_load_timeout(5)
                self.driver.get(target_url)
            except TimeoutException:
                print("页面加载超时，但可能已部分加载，继续执行...")
            except Exception as e:
                print(f"访问页面失败: {e}")
                return False
            
            # 等待页面基本加载
            time.sleep(2)
            
            # 优化页面加载
            self.optimize_page_loading()
            
            # 关闭弹窗 - 使用更可靠的方法
            print("尝试关闭弹窗...")
            try:
                actions = ActionChains(self.driver)
                actions.send_keys(Keys.ESCAPE).perform()
                time.sleep(0.5)
                print("尝试ESC键关闭")
            except:
                pass

            # 开始游戏
            print("\n加载候选等式...")
            candidates = self.all_candidates[:]
            print(f"✓ 共加载 {len(candidates)} 个候选等式")
            
            # 创建历史记录
            history = GameHistory(answer="", steps=[])
            
            answer = None
            first_guess = "1+56/7=9"
            
            for attempt in range(6):
                print(f"\n=== 第 {attempt + 1}/6 次尝试 ===")
                
                # 选择猜测
                if attempt == 0:
                    guess = first_guess
                else:
                    guess = self.suggest_next_guess(candidates, history.steps)
                    if not guess and candidates:
                        guess = candidates[0]
                    elif not guess:
                        guess = "12+45=57"  # 备用猜测
                
                print(f"猜测: {guess}")
                
                # 键盘输入
                try:
                    # 确保页面有焦点
                    self.driver.execute_script("window.focus();")
                    time.sleep(0.2)
                    
                    # 使用JavaScript输入作为备选
                    try:
                        body = WebDriverWait(self.driver, 3).until(
                            EC.presence_of_element_located((By.TAG_NAME, 'body'))
                        )
                        for char in guess:
                            body.send_keys(char)
                            time.sleep(0.1)
                        body.send_keys(Keys.RETURN)
                        print(f"✓ 输入完成")
                    except:
                        # 如果常规输入失败，尝试JavaScript
                        print("常规输入失败，尝试JavaScript输入...")
                        for char in guess:
                            self.driver.execute_script(f"document.activeElement.value += '{char}';")
                            time.sleep(0.1)
                        self.driver.execute_script("""
                        var e = new KeyboardEvent('keydown', {key: 'Enter', keyCode: 13});
                        document.dispatchEvent(e);
                        """)
                except Exception as e:
                    print(f"✗ 输入失败: {e}")
                    # 尝试备用方法
                    try:
                        body = self.driver.find_element(By.TAG_NAME, 'body')
                        body.send_keys(guess + Keys.RETURN)
                    except Exception as e2:
                        print(f"备用输入也失败: {e2}")
                        return None
                
                # 获取反馈
                feedback = self.get_feedback_from_page(attempt, guess)
                if not feedback:
                    print("⚠️ 无法获取反馈，使用模拟反馈")
                    # 简单模拟反馈：全部设为absent
                    feedback = [{"char": guess[i], "status": "absent"} for i in range(8)]
                
                print(f"反馈: {[fb['status'] for fb in feedback]}")
                
                # 检查是否全部正确
                if all(fb.get('status') == 'correct' for fb in feedback):
                    answer = guess
                    print(f"🎉 找到答案: {answer}")
                    
                    step = GameStep(
                        guess=guess,
                        feedback=feedback,
                        candidate_count=1,
                        next_suggestion=""
                    )
                    history.steps.append(step)
                    history.answer = answer
                    break
                
                # 过滤候选
                new_candidates = []
                for cand in candidates:
                    simulated = self.nerdle_feedback(cand, guess)
                    
                    ok = True
                    for i in range(8):
                        if simulated[i]["status"] != feedback[i]["status"]:
                            ok = False
                            break
                    
                    if ok:
                        new_candidates.append(cand)
                
                candidates = new_candidates
                print(f"剩余候选: {len(candidates)} 个")
                
                if candidates and len(candidates) <= 10:
                    print(f"候选示例: {candidates}")
                
                # 建议下一个猜测
                next_guess = ""
                if candidates:
                    if len(candidates) == 1:
                        next_guess = candidates[0]
                    else:
                        next_guess = self.suggest_next_guess(candidates, history.steps)
                
                # 创建步骤记录
                step = GameStep(
                    guess=guess,
                    feedback=feedback,
                    candidate_count=len(candidates),
                    next_suggestion=next_guess
                )
                history.steps.append(step)
                
                # 如果没有候选了，结束游戏
                if not candidates:
                    print("⚠️ 没有候选等式了")
                    break
            
            # 确定最终答案
            if not answer and history.steps:
                if candidates:
                    answer = candidates[0]
                else:
                    answer = history.steps[-1].guess
            
            # 更新历史记录中的答案
            history.answer = answer or "未知"
            
            return history
            
        except Exception as e:
            print(f"❌ 游戏执行出错: {e}")
            traceback.print_exc()
            return None
            
        finally:
            if self.driver:
                try:
                    print("正在关闭浏览器...")
                    self.driver.quit()
                    print("✓ 浏览器已关闭")
                except:
                    print("✗ 关闭浏览器时出错")