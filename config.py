import json
import os

from paths import CONFIG_PATH

CONFIG_FILE = CONFIG_PATH  # 兼容旧引用（绝对路径，不再依赖 CWD）

def save_config(config):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def load_config():
    default_config = {
        "delay_ms": 500,
        "offset_px": 5,
        "mode1": '无',
        "max_runtime": -1.0,
        "mode2":'只打加成',
        "accel": True,
        "mumu_path": r"D:\Program Files\Netease\MuMu",
        "ld_path": ""
    }

    if not os.path.exists(CONFIG_PATH):
        return default_config

    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 补全缺失字段
        for key in default_config:
            if key not in config:
                config[key] = default_config[key]

        # 剔除已废弃字段（screenshot_enhance 已由自动链式取代）
        config.pop("screenshot_enhance", None)

        return config

    except Exception:
        # 任何异常均返回默认配置
        return default_config
