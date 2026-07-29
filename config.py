import json
import os

CONFIG_FILE = "config.json"

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def load_config():
    default_config = {
        "delay_ms": 500,
        "offset_px": 5,
        "mode1": '无',
        "max_runtime": -1.0,
        "mode2":'只打加成',
        "accel": True
    }

    if not os.path.exists(CONFIG_FILE):
        return default_config

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # 补全缺失字段
        for key in default_config:
            if key not in config:
                config[key] = default_config[key]


        return config

    except Exception:
        # 任何异常均返回默认配置
        return default_config
