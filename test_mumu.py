import sys, time
sys.path.insert(0, '.')
from adb.mumu_extras import MuMuExtras
import cv2

path = r"D:\Program Files\Netease\MuMu"
print("is_supported:", MuMuExtras.is_supported(), flush=True)
print("find_dll:", MuMuExtras.find_dll(path), flush=True)
print("get_mumu_index(emulator-5554):", MuMuExtras.get_mumu_index("emulator-5554"), flush=True)

try:
    t0 = time.time()
    extras = MuMuExtras(path, 0)
    print(f"connected in {time.time()-t0:.2f}s, display: {extras._width} x {extras._height}", flush=True)
    t1 = time.time()
    img = extras.screencap()
    print(f"screencap in {time.time()-t1:.3f}s, shape: {img.shape} dtype: {img.dtype}", flush=True)
    cv2.imwrite("mumu_test.png", img)
    print("saved mumu_test.png", flush=True)
    extras.close()
except Exception as e:
    import traceback; traceback.print_exc()
    print("ERROR:", type(e).__name__, e, flush=True)
