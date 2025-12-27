# 由 nonebot_plugin_nerdle 的 __init__.py 改变而来
import asyncio
import time
import json
from datetime import datetime, timedelta
from typing import Annotated, Any
from pathlib import Path

from nonebot import on_command, require, get_driver, get_bots
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot.utils import run_sync

require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")

from nonebot_plugin_alconna import (
    AlcMatches,
    Alconna,
    AlconnaQuery,
    Args,
    At,
    Image,
    Option,
    Query,
    Text,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from .data_source import NerdleAutoPlayer, GameHistory

__version__ = "0.1.0"

__plugin_meta__ = PluginMetadata(
    name="nerdle演示",
    description="自动玩nerdle猜等式游戏，演示完整交互过程",
    usage=(
        "@我/私聊 + \"nerdle autoplay\"开始自动游戏\n"
        "@我/私聊 + \"nerdle 清除缓存\"清除当前窗口缓存（仅超级管理员）\n"
        "@我/私聊 + \"nerdle 全局清除缓存\"清除所有缓存（仅超级管理员）\n"
        "插件将自动访问 nerdlegame.com，模拟完整游戏过程\n"
        "每日首次运行会缓存结果，后续调用直接返回缓存\n"
        "相邻消息间隔 5 秒，展示每一步的猜测和反馈"
    ),
    type="application",
    homepage="https://github.com/Lovable-xlz/nonebot_plugin_nerdle_autoplay/tree/main",
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna", "nonebot_plugin_uninfo"
    ),
    extra={
        "requires": ["selenium>=4.0.0", "webdriver-manager>=3.0.0", "pillow>=9.0.0"]
    }
)

# 缓存目录
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

def get_user_id(uninfo: Uninfo) -> str:
    return f"{uninfo.scope}_{uninfo.self_id}_{uninfo.scene_path}"

UserId = Annotated[str, Depends(get_user_id)]

def get_cache_file(user_id: str, timestamp: datetime = None) -> Path:
    """获取用户缓存文件路径（精确到分钟）"""
    if timestamp is None:
        timestamp = datetime.now()
    # 格式：用户ID_年月日_时分.json
    time_str = timestamp.strftime("%Y-%m-%d_%H-%M")
    return CACHE_DIR / f"{user_id}_{time_str}.json"

def is_cache_valid(cache_file: Path) -> bool:
    """检查缓存是否有效（在当天8点之后创建）"""
    if not cache_file.exists():
        return False
    
    try:
        # 从文件名中提取时间
        filename = cache_file.stem
        # 格式：用户ID_年月日_时分
        parts = filename.split('_')
        if len(parts) < 3:
            return False
        
        date_str = parts[-2]  # 年月日
        time_str = parts[-1]  # 时分
        
        # 解析日期时间
        cache_datetime = datetime.strptime(f"{date_str}_{time_str}", "%Y-%m-%d_%H-%M")
        
        # 获取缓存日期的8点
        cache_date_8am = datetime(cache_datetime.year, cache_datetime.month, cache_datetime.day, 8, 0)
        
        # 检查是否在8点之后创建
        return cache_datetime >= cache_date_8am
    except Exception as e:
        logger.error(f"检查缓存有效性失败: {e}")
        return False

def load_cached_result(user_id: str) -> GameHistory | None:
    """加载缓存结果"""
    try:
        # 查找用户的所有缓存文件
        cache_pattern = f"{user_id}_*.json"
        cache_files = list(CACHE_DIR.glob(cache_pattern))
        
        if not cache_files:
            return None
        
        # 按修改时间排序，最新的在前
        cache_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        # 检查每个缓存文件的有效性
        valid_caches = []
        for cache_file in cache_files:
            if is_cache_valid(cache_file):
                valid_caches.append(cache_file)
            else:
                # 删除无效缓存（8点之前的）
                try:
                    cache_file.unlink()
                    logger.info(f"删除无效缓存: {cache_file.name}")
                except Exception as e:
                    logger.error(f"删除缓存失败: {e}")
        
        if not valid_caches:
            return None
        
        # 使用最新的有效缓存
        latest_cache = valid_caches[0]
        try:
            with open(latest_cache, 'r', encoding='utf-8') as f:
                data = json.load(f)
                history = GameHistory.from_dict(data)
                logger.info(f"加载缓存: {latest_cache.name}")
                return history
        except Exception as e:
            logger.error(f"加载缓存文件失败: {e}")
            # 如果加载失败，删除损坏的缓存文件
            try:
                latest_cache.unlink()
            except:
                pass
            return None
    except Exception as e:
        logger.error(f"加载缓存结果失败: {e}")
        return None

def save_cached_result(user_id: str, history: GameHistory):
    """保存缓存结果（如果在7:55~8:05之间则不保存）"""
    now = datetime.now()
    
    # 检查是否在7:55~8:05之间
    current_time = now.time()
    no_cache_start = datetime.strptime("07:55", "%H:%M").time()
    no_cache_end = datetime.strptime("08:05", "%H:%M").time()
    
    if no_cache_start <= current_time <= no_cache_end:
        logger.info(f"当前时间 {current_time} 在7:55~8:05之间，不保存缓存")
        return
    
    try:
        # 删除用户的所有旧缓存
        cache_pattern = f"{user_id}_*.json"
        for old_cache in CACHE_DIR.glob(cache_pattern):
            try:
                old_cache.unlink()
                logger.info(f"删除旧缓存: {old_cache.name}")
            except Exception as e:
                logger.error(f"删除旧缓存失败: {e}")
        
        # 创建新缓存
        cache_file = get_cache_file(user_id, now)
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(history.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"保存缓存: {cache_file.name}")
    except Exception as e:
        logger.error(f"保存缓存失败: {e}")

def clean_old_caches():
    """清理所有8点以前的缓存文件"""
    try:
        cache_files = list(CACHE_DIR.glob("*.json"))
        deleted_count = 0
        
        for cache_file in cache_files:
            if not is_cache_valid(cache_file):
                try:
                    cache_file.unlink()
                    deleted_count += 1
                    logger.info(f"清理过期缓存: {cache_file.name}")
                except Exception as e:
                    logger.error(f"清理缓存失败: {e}")
        
        if deleted_count > 0:
            logger.info(f"共清理 {deleted_count} 个过期缓存文件")
    except Exception as e:
        logger.error(f"清理缓存时出错: {e}")

from arclet.alconna import Alconna, Args, CommandMeta

# 创建 Alconna 命令
autoplay_alc_command = Alconna(
    "nerdle autoplay",
    Args["force?", bool],
    meta=CommandMeta(
        description="nerdle自动游戏",
        example="nerdle autoplay [--force]",
    ),
)

# 创建清除缓存的命令
clear_cache_alc_command = Alconna(
    "nerdle 清除缓存",
    meta=CommandMeta(
        description="清除个人nerdle缓存（仅超级管理员）",
        example="nerdle 清除缓存",
    ),
)

# 创建全局清除缓存的命令
clear_all_cache_alc_command = Alconna(
    "nerdle 全局清除缓存",
    meta=CommandMeta(
        description="清除所有nerdle缓存（仅超级管理员）",
        example="nerdle 全局清除缓存",
    ),
)

# 创建匹配器
matcher_autoplay = on_alconna(
    autoplay_alc_command,
    use_cmd_start=True,
    block=True,
    priority=13,
)

matcher_clear_cache = on_alconna(
    clear_cache_alc_command,
    use_cmd_start=True,
    block=True,
    priority=13,
    permission=SUPERUSER,  # 仅超级管理员可用
)

matcher_clear_all_cache = on_alconna(
    clear_all_cache_alc_command,
    use_cmd_start=True,
    block=True,
    priority=13,
    permission=SUPERUSER,  # 仅超级管理员可用
)

@matcher_autoplay.handle()
async def _(
    matcher: Matcher,
    user_id: UserId,
    alc_matches: AlcMatches,
    force: Query[bool] = AlconnaQuery("force", False),
):
    # 先清理过期缓存
    await run_sync(clean_old_caches)()
    
    # 检查是否强制重新运行
    if not force.result:
        # 尝试加载缓存
        cached_history = load_cached_result(user_id)
        if cached_history:
            logger.info(f"用户 {user_id} 使用缓存结果")
            await send_cached_result(matcher, cached_history)
            return
    
    # 显示开始消息
    await UniMessage.text("🚀🚀 开始 Nerdle Autoplay...").send()
    await asyncio.sleep(1)
    
    # 创建自动玩家
    player = NerdleAutoPlayer()
    
    try:
        # 运行自动游戏（在异步线程中执行同步代码）
        await UniMessage.text("🤓👆 正在启动浏览器并游玩，预计需要 5 分钟时间，请耐心等待...").send()
        await asyncio.sleep(1)
        
        history = await run_sync(player.run_auto_game)()
        
        if history:
            # 保存缓存
            save_cached_result(user_id, history)
            
            # 发送最终结果
            await send_auto_game_result(matcher, history)
        else:
            await UniMessage.text("❌ 自动游戏失败，请稍后重试").send()
            
    except Exception as e:
        logger.error(f"自动游戏异常: {e}")
        await UniMessage.text(f"❌ 游戏执行出错: {e}").send()

@matcher_clear_cache.handle()
async def handle_clear_cache(
    matcher: Matcher,
    user_id: UserId,
):
    """清除个人缓存"""
    try:
        # 查找用户的所有缓存文件
        cache_pattern = f"{user_id}_*.json"
        cache_files = list(CACHE_DIR.glob(cache_pattern))
        
        if not cache_files:
            await UniMessage.text("您没有 nerdle 缓存文件").send()
            return
        
        deleted_count = 0
        for cache_file in cache_files:
            try:
                cache_file.unlink()
                deleted_count += 1
                logger.info(f"删除缓存: {cache_file.name}")
            except Exception as e:
                logger.error(f"删除缓存失败: {e}")
        
        await UniMessage.text(f"已清除 {deleted_count} 个您的 nerdle 缓存文件").send()
        
    except Exception as e:
        logger.error(f"清除缓存失败: {e}")
        await UniMessage.text(f"❌ 清除缓存失败: {e}").send()

@matcher_clear_all_cache.handle()
async def handle_clear_all_cache(matcher: Matcher):
    """全局清除所有缓存"""
    try:
        cache_files = list(CACHE_DIR.glob("*.json"))
        
        if not cache_files:
            await UniMessage.text("📭 没有nerdle缓存文件").send()
            return
        
        deleted_count = 0
        for cache_file in cache_files:
            try:
                cache_file.unlink()
                deleted_count += 1
                logger.info(f"删除缓存: {cache_file.name}")
            except Exception as e:
                logger.error(f"删除缓存失败: {e}")
        
        await UniMessage.text(f"✅ 已全局清除 {deleted_count} 个nerdle缓存文件").send()
        
    except Exception as e:
        logger.error(f"全局清除缓存失败: {e}")
        await UniMessage.text(f"❌ 全局清除缓存失败: {e}").send()

async def send_auto_game_result(matcher: Matcher, history: GameHistory):
    """发送自动游戏结果"""
    # 逐步发送每一步的过程
    await UniMessage.text(f"✍✍ 游戏结束，共进行了 {len(history.steps)} 次尝试").send()
    await asyncio.sleep(1)
    
    for i, step in enumerate(history.steps, 1):
        await UniMessage.text(f"第 {i} 次尝试: {step.guess}").send()
        await asyncio.sleep(2)
        
        # 使用 render_step_image 渲染当前步骤的状态
        step_image = await run_sync(history.render_step_image)(i - 1)  # i-1 因为索引从0开始
        await UniMessage.image(raw=step_image).send()
        await asyncio.sleep(3)  # 每条消息间隔3秒
    
    # 发送最终结果
    # 使用 render_final_image 渲染最终状态
    final_image = await run_sync(history.render_final_image)()
    result_text = f"🎉🎉🎉 游戏结束！最终答案: {history.answer}"
    
    await (
        UniMessage.template("{result}\n{image}")
        .format(result=result_text, image=Image(raw=final_image))
        .send()
    )

async def send_cached_result(matcher: Matcher, history: GameHistory):
    """发送缓存结果"""
    await UniMessage.text("📅 使用今日缓存结果:").send()
    await asyncio.sleep(1)
    
    # 发送最终结果
    final_image = await run_sync(history.render_final_image)()
    result_text = f"最终答案: {history.answer}"
    
    await (
        UniMessage.template("😋😋 {result}\n{image}")
        .format(result=result_text, image=Image(raw=final_image))
        .send()
    )

# 在插件加载时清理过期缓存
@get_driver().on_startup
async def startup_cleanup():
    """启动时清理过期缓存"""
    logger.info("启动时清理nerdle过期缓存...")

    await run_sync(clean_old_caches)()
