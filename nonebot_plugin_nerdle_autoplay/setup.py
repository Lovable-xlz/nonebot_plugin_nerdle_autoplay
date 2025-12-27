from setuptools import setup, find_packages

setup(
    name="nonebot_plugin_nerdle_autoplay",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "selenium>=4.15.0",
        "pillow>=10.1.0",
        "webdriver-manager>=4.0.1"
    ],
    entry_points={
        "nonebot.plugin": [
            "nerdle_autoplay = nonebot_plugin_nerdle_autoplay"
        ]
    },
)