from adb.adb_client import ADBClient
from adb.screenshot import ScreenCapturer
from PIL import Image
import io

devices = ADBClient.list_devices()
print("Devices:", devices)

client = ADBClient(devices[0])
capturer = ScreenCapturer(client)

img = capturer.capture()
print("Image shape:", img.shape)

# 将OpenCV格式的图像（BGR）转换为PIL格式（RGB）
pil_img = Image.fromarray(img[:, :, ::-1])

# 移除存在问题的icc_profile信息
if 'icc_profile' in pil_img.info:
    pil_img.info.pop('icc_profile')

# 保存修复后的图片
pil_img.save("test.png")