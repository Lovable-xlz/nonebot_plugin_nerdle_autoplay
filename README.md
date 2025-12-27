# nonebot_plugin_nerdle_autoplay
Nerdle 小游戏自动演示

## 安装步骤（Windows 环境下，对 Linux 的兼容性未知）
1. 将文件夹 `nonebot_plugin_nerdle_autoplay` 下载并移动到你的项目所在目录 `.\.venv\Lib\site-packages` 下
2. 打开终端，在项目根目录输入 `pip install -e .\.venv\Lib\site-packages\nonebot_plugin_nerdle_autoplay` 以安装该插件。

   请确保你的环境中存在 `setuptools` 和 `wheel` 库！
3. 在你的项目的 `pyproject.toml` 中添加如下内容：

```python
dependencies = [
    "nonebot-plugin-nerdle-autoplay>=0.1.0",
    # 其余部分保持你的内容不变
]


nonebot-plugin-nerdle-autoplay = ["nonebot_plugin_nerdle_autoplay"]
```

4. 运行你的项目，检查是否能正常加载该插件。

#### 请一定确保你的项目虚拟环境下已正确安装了 `selenium` `webdriver-manager` `pillow` 库！！！

#### （检查方法：确认 `.\.venv\Lib\site-packages` 目录下是否存在三个库的对应文件夹）

## 使用教程

`@bot/私聊` + `nerdle autoplay` 开始自动演示；

仅 SUPERUSER 可用：

`@bot/私聊` + `nerdle 清除缓存` 清除当前对话缓存；

`@bot/私聊` + `nerdle 全局清除缓存` 清除所有缓存。

-----------

插件将自动访问 https://nerdlegame.com，模拟完整游戏过程，并随后展示每一步的猜测和反馈。

每日首次运行会缓存结果，后续调用直接返回缓存（缓存每日 8 点刷新，8 点附近的调用记录不会被缓存以防止日期出错）。

#### 请根据运行设备性能自行修改 `data_source.py` 中几个 `sleep` 和 `timeout` 函数的参数，以保证该插件可以正常运行！（`click_nerdle.py` 同理）

## `click_nerdle.py` 说明

打开终端，在该代码所在目录下输入 `python click_nerdle.py` 以开始本地演示。

#### 请一定确保你的本地环境下已正确安装了 `selenium` `webdriver-manager` `pillow` 库！！！

## 其他说明

关于 `/nonebot_plugin_nerdle_autoplay/resources` 下的文件生成，请参考 https://github.com/Lovable-xlz/nonebot_plugin_nerdle 仓库中的 `cpp` 文件。
