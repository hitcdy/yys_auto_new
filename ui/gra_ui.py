import gradio as gr
import time
import subprocess
from config import load_config, save_config
from core.device_assembler import assemble_device
from vision.ocr_engine import OCREngine
from adb.adb_client import ADBClient

_ocr_engine = None

def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        print("[OCR] 初始化 Tesseract...")
        _ocr_engine = OCREngine(debug=True)
        print("[OCR] 初始化完成")
    return _ocr_engine

def create_ui(template_paths):
    """
    创建多设备 Tab 分页 UI（静态 4 个标签页）
    template_paths: 模板路径字典，所有设备共享
    """
    config = load_config()
    
    # 存储每个标签页对应的 BotController 实例
    controllers = [None] * 4  # 索引 0~3
    
    with gr.Blocks() as demo:
        with gr.Tabs():
            for idx in range(1, 5):  # 创建 4 个标签页
                with gr.TabItem(f"设备 {idx}"):
                    with gr.Row():
                        with gr.Column():
                            choose = gr.Dropdown(
                                choices=[],
                                label="设备选择",
                                interactive=True
                            )
                            with gr.Row():
                                connect_btn = gr.Button(value='连接')
                                refresh_btn = gr.Button(value='刷新设备')
                                restart_adb_btn = gr.Button(value='重启 ADB')
                            
                            delay = gr.Textbox(
                                label='随机延迟最大值(ms)',
                                value=str(config["delay_ms"]),
                                interactive=True
                            )
                            click_offset = gr.Textbox(
                                label='点击偏移(像素)',
                                value=str(config["offset_px"]),
                                interactive=True
                            )
                            mode1 = gr.Radio(
                                label='功能选择',
                                choices=['无', '券满暂停', '自动突破', '仅突破', '爬塔', '御灵', '寮突'],
                                value=str(config["mode1"]),
                                interactive=True
                            )
                            max_runtime = gr.Number(
                                label='最大运行时长(分，负数表示无限)',
                                value=config["max_runtime"],
                                interactive=True
                            )
                            mode2 = gr.Radio(
                                label='探索模式',
                                choices=['只打加成', '全打'],
                                value=str(config["mode2"]),
                                interactive=True
                            )
                            accel = gr.Radio(
                                label='加速',
                                choices=['加速', '非加速'],
                                value='加速' if config.get("accel", True) else '非加速',
                                interactive=True
                            )
                            mumu_path = gr.Textbox(
                                label='MuMu 安装路径',
                                value=config.get("mumu_path", r"D:\Program Files\Netease\MuMu"),
                                interactive=True
                            )
                            ld_path = gr.Textbox(
                                label='雷电安装路径（留空自动探测）',
                                value=config.get("ld_path", ""),
                                interactive=True
                            )
                            gr.Markdown(
                                "> 截图/触摸强化自动启用，无需手动勾选：截图按序尝试 MuMu → 雷电 → ADB；"
                                "触摸按序尝试 MuMu → minitouch → ADB。前者不可用自动跳过，不报错。"
                                "MuMu 路径需含 external_renderer_ipc.dll；雷电路径需含 ldopengl64.dll。"
                            )
                            shutdown_cb = gr.Checkbox(
                                label='达到最大运行时长后自动关机（默认关闭，每次需手动勾选）',
                                value=False,
                                interactive=True
                            )
                            submit_btn = gr.Button(value='提交参数')
                            start_btn = gr.Button(value='开始')
                            stop_btn = gr.Button(value='暂停')
                        
                        with gr.Column():
                            ot1 = gr.Textbox(label="循环次数", interactive=False)
                            ot2 = gr.Textbox(label="运行时间", interactive=False)
                            ot3 = gr.Textbox(label="脚本状态", interactive=False)
                            ot4 = gr.Textbox(label="当前状态机", interactive=False)
                            ot5 = gr.Textbox(label="战斗次数", interactive=False)
                    
                    # 定义该标签页的回调函数（使用闭包捕获 idx）
                    def get_devices():
                        devices = ADBClient.list_devices()
                        return gr.update(choices=devices)
                    
                    def connect_device(device, mumu_path_val, ld_path_val, i=idx-1):
                        if not device:
                            return "未选择设备"
                        try:
                            adb, capturer, matcher, detector, game_ctrl, bot, status = assemble_device(
                                device, mumu_path=mumu_path_val or "", ld_path=ld_path_val or "",
                                ocr_engine=_get_ocr_engine()
                            )
                            # 加载模板（所有设备共享同一套模板）
                            matcher.load_templates(template_paths)
                            controllers[i] = bot
                            # 应用当前控件的配置
                            try:
                                delay_ms = float(delay.value)
                                offset_px = int(click_offset.value)
                                mode1_val = mode1.value
                                mode2_val = mode2.value
                                accel_val = (accel.value == '加速')
                                delay_range = (0, delay_ms / 1000)
                                bot.update_random_config(delay_range, (offset_px, offset_px), mode1_val, mode2_val, accel_val)
                            except Exception as e:
                                print(f"应用配置失败: {e}")
                            return status
                        except Exception as e:
                            return f"连接失败: {e}"
                    
                    def restart_adb_func(i=idx-1):
                        bot = controllers[i]
                        if bot and bot.is_running():
                            return gr.update(), "脚本正在运行，无法重启 ADB"
                        try:
                            subprocess.run(["adb", "kill-server"], timeout=5, stderr=subprocess.PIPE)
                            time.sleep(1)
                            devices = ADBClient.list_devices()
                            return gr.update(choices=devices), "ADB 服务已重启"
                        except Exception as e:
                            return gr.update(), f"重启 ADB 失败: {e}"
                    
                    def submit_config(delay_ms, offset_px, mode1_val, max_runtime_val, mode2_val, accel_val, mumu_path_val, ld_path_val, i=idx-1):
                        try:
                            delay_ms = float(delay_ms)
                            offset_px = int(offset_px)
                            max_runtime_val = float(max_runtime_val)
                        except:
                            return "参数错误"
                        bot = controllers[i]
                        if bot:
                            delay_range = (0, delay_ms / 1000)
                            accel_bool = (accel_val == '加速')
                            bot.update_random_config(delay_range, (offset_px, offset_px), mode1_val, mode2_val, accel_bool)
                            save_config({
                                "delay_ms": delay_ms,
                                "offset_px": offset_px,
                                "mode1": mode1_val,
                                "max_runtime": max_runtime_val,
                                "mode2": mode2_val,
                                "accel": accel_bool,
                                "mumu_path": mumu_path_val or "",
                                "ld_path": ld_path_val or ""
                            })
                        return "参数已更新"
                    
                    def start_bot(max_runtime_val, shutdown_val, i=idx-1):
                        if max_runtime_val is None:
                            max_runtime_val = -1.0
                        bot = controllers[i]
                        if bot:
                            bot.start(
                                max_runtime=60 * float(max_runtime_val),
                                shutdown_on_timeout=bool(shutdown_val)
                            )
                            # 关机开关仅本次启动生效，启动后立即复位，下次需重新勾选
                            return "运行中", False
                        return "请先连接设备", False
                    
                    def stop_bot(i=idx-1):
                        bot = controllers[i]
                        if bot:
                            bot.stop()
                            return "已暂停"
                        return "未连接"
                    
                    def refresh_status(i=idx-1):
                        bot = controllers[i]
                        if bot:
                            return (
                                f"{bot.get_cycle_times()}",
                                f"{bot.get_operating_time()} s",
                                f"{bot.get_state()}",
                                f"{bot.get_states()}",
                                f"{bot.get_win_cnts()}"
                            )
                        else:
                            return ("0", "0 s", "未连接", "无", "0")
                    
                    # 绑定事件
                    refresh_btn.click(fn=get_devices, outputs=choose)
                    restart_adb_btn.click(fn=restart_adb_func, outputs=[choose, ot3])
                    connect_btn.click(fn=connect_device, inputs=[choose, mumu_path, ld_path], outputs=ot3)
                    submit_btn.click(fn=submit_config, inputs=[delay, click_offset, mode1, max_runtime, mode2, accel, mumu_path, ld_path], outputs=ot3)
                    start_btn.click(fn=start_bot, inputs=[max_runtime, shutdown_cb], outputs=[ot3, shutdown_cb])
                    stop_btn.click(fn=stop_bot, outputs=ot3)
                    
                    timer = gr.Timer(1.0)
                    timer.tick(fn=refresh_status, outputs=[ot1, ot2, ot3, ot4, ot5])
                    
                    # 页面加载时自动获取设备列表
                    demo.load(fn=get_devices, outputs=choose)
    return demo