"""
PC Game Auto Map Script
核心逻辑:
- 使用 MSS 截屏
- 使用 OpenCV 模板匹配 (阈值 0.85)
- 使用 PyDirectInput 点击，带随机偏移以防检测
- 基于状态机实现推图自动化: 失败/再战 -> 选阵容 -> 一键采用 -> 自动挑战；
- 自动战斗结束后点击空白处再重试

全局变量:
- formation_index: 记录当前应选择第几个推荐阵容，最多 3 个阵容
"""

from __future__ import annotations

import cv2
import numpy as np
import time
import random
import os
import mss
import pydirectinput
import logging

# ------------------------------ 配置与常量 ------------------------------
# 日志配置
logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] %(levelname)s: %(message)s',
                    handlers=[logging.FileHandler("auto_map_game.log", encoding='utf-8'),
                              logging.StreamHandler()])

def _log_info(msg: str) -> None:
    logging.info(msg)

def _log_error(msg: str) -> None:
    logging.error(msg)
# 最小证据阈值
THRESHOLD = 0.85
# per-template thresholds (basename -> threshold)
THRESHOLD_MAP = {
    'formation_btn.png': 0.88,
    'formation_1.png': 0.85,
    'formation_2.png': 0.85,
    'formation_3.png': 0.85,
    'auto_battle_end.png': 0.86,
    'retry.png': 0.85,
    'challenge_failed.png': 0.85,
    'one_key_use.png': 0.85,
    'auto_challenge.png': 0.85,
}

# 全局状态：阵容索引，0..2
formation_index = 0
MAX_FORMATIONS = 3

# 模板图片文件名（放在脚本同目录下，或在脚本中给出正确相对路径）
# 程序会逐项尝试在当前屏幕截图中匹配这些模板。
TEMPLATES = {
    # 状态检测
    'challenge_failed': 'challenge_failed.png',  # 挑战失败
    'retry': 'retry.png',                        # 再次挑战
    'auto_battle_end': 'auto_battle_end.png',    # 自动战斗结束提示
    # 流程控制
    'formation_btn': 'formation_btn.png',        # 通关阵容按钮
    'formation_1': 'formation_1.png',            # 第1个阵容模板
    'formation_2': 'formation_2.png',            # 第2个阵容模板
    'formation_3': 'formation_3.png',            # 第3个阵容模板
    'one_key_use': 'one_key_use.png',            # 一键采用
    'auto_challenge': 'auto_challenge.png',      # 自动挑战
}


# 全局图片搜索区域(监视器)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 监视器设置（通常为主显示器，索引 1）
_sct = mss.mss()
MONITOR = _sct.monitors[1]

# 暂停/继续开关（可通过 F8 快捷键触发）
PAUSED = False
try:
    import threading as _threading
    import keyboard as _keyboard  # type: ignore
    def _toggle_pause():
        global PAUSED
        PAUSED = not PAUSED
        _log_info(f"Pause toggled: now {'PAUSED' if PAUSED else 'RUNNING'}")
    _keyboard.add_hotkey('F8', _toggle_pause)
    _log_info("Pause hotkey attached: F8")
except Exception:
    # 无法安装热键时回退：仅在脚本内变更暂停状态
    _log_info("Pause hotkey not available; running without hotkey support.")

# 模板缓存
TEMPLATE_CACHE: dict[str, np.ndarray] = {}


def _load_template(path: str) -> np.ndarray | None:
    if not path:
        return None
    # 1) 尝试同目录路径
    full = os.path.join(BASE_DIR, path) if not os.path.isabs(path) else path
    if not os.path.exists(full):
        # 2) 尝试 templates/ 子目录作为容错路径
        alt = os.path.join(BASE_DIR, 'templates', path) if not os.path.isabs(path) else path
        if os.path.exists(alt):
            full = alt
        else:
            return None
    # 使用缓存
    if full in TEMPLATE_CACHE:
        return TEMPLATE_CACHE[full]
    img = cv2.imread(full, cv2.IMREAD_GRAYSCALE)
    if img is not None:
        TEMPLATE_CACHE[full] = img
    return img


def _template_threshold(template_path: str) -> float:
    base = os.path.basename(template_path)
    return THRESHOLD_MAP.get(base, THRESHOLD)


def _grab_gray() -> np.ndarray:
    # 捕获主监视器区域的截图并转为灰度图
    sct_img = _sct.grab(MONITOR)
    frame = np.array(sct_img)  # BGRA
    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    return gray


def _find_template_on_screen(template_path: str, threshold: float = THRESHOLD) -> tuple[bool, tuple[int, int], tuple[int, int]]:
    """返回 (found, (x, y), (w, h))，若未找到返回 (False, (0,0), (0,0))"""
    tmpl_orig = _load_template(template_path)
    if tmpl_orig is None:
        return False, (0, 0), (0, 0)
    gray = _grab_gray()
    # 多尺度匹配以提高鲁棒性
    scales = [1.0, 0.95, 1.05, 0.9, 1.1]
    best_val = -1.0
    best_loc = (0, 0)
    best_w, best_h = 0, 0
    for sc in scales:
        try:
            w = max(1, int(tmpl_orig.shape[1] * sc))
            h = max(1, int(tmpl_orig.shape[0] * sc))
            tmpl = cv2.resize(tmpl_orig, (w, h), interpolation=cv2.INTER_LINEAR)
        except Exception:
            continue
        if w < 2 or h < 2:
            continue
        res = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
        minVal, maxVal, minLoc, maxLoc = cv2.minMaxLoc(res)
        if maxVal > best_val:
            best_val = maxVal
            best_loc = maxLoc
            best_w, best_h = w, h
    if best_val >= threshold:
        return True, best_loc, (best_w, best_h)
    return False, (0, 0), (0, 0)


def _find_all_template_matches(template_path: str, threshold: float = THRESHOLD) -> list[tuple[int, int, int, int]]:
    """返回所有匹配点的列表 [(x, y, w, h), ...]，并进行简单去重，返回按 y 坐标排序的列表"""
    tmpl = _load_template(template_path)
    if tmpl is None:
        return []
    gray = _grab_gray()
    res = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
    # 使用 per-template threshold
    thr = _template_threshold(template_path) if threshold == THRESHOLD else threshold
    ys, xs = (np.where(res >= thr))
    w, h = tmpl.shape[1], tmpl.shape[0]
    matches = []
    for y, x in zip(ys, xs):
        matches.append((int(x), int(y), int(w), int(h)))
    # 简单去重：按 (x,y) 的最近距离聚类
    filtered: list[tuple[int, int, int, int]] = []
    for m in sorted(matches, key=lambda t: (t[1], t[0])):
        if not any(abs(m[0]-f[0]) < 20 and abs(m[1]-f[1]) < 20 for f in filtered):
            filtered.append(m)
    return filtered


def _random_click_at(x: int, y: int, w: int, h: int) -> None:
    """在目标区域(x,y,w,h)内以随机偏移点击中心点"""
    cx = x + w // 2
    cy = y + h // 2
    offset_x = random.randint(-max(1, w // 4), w // 4)
    offset_y = random.randint(-max(1, h // 4), h // 4)
    gx = int(cx + offset_x)
    gy = int(cy + offset_y)
    # tiny jitter before click
    time.sleep(random.uniform(0.05, 0.15))
    # PyDirectInput 的点击通常是绝对坐标
    pydirectinput.moveTo(gx, gy, duration=0.05)
    pydirectinput.click()


def _click_random_blank_area() -> None:
    width = MONITOR[2]
    height = MONITOR[3]
    # 选择一个随机位置，尽量避开边界，模拟空白处点击以关闭提示
    rx = random.randint(100, max(100, width - 100))
    ry = random.randint(100, max(100, height - 100))
    _random_click_at(rx - 20, ry - 20, 40, 40)


def _click_template(template_key: str) -> bool:
    path = TEMPLATES.get(template_key, '')
    if not path:
        return False
    found, loc, wh = _find_template_on_screen(path, _template_threshold(path))
    if found:
        _random_click_at(loc[0], loc[1], wh[0], wh[1])
        time.sleep(random.uniform(0.5, 1.5))  # 点击后延时，防检测
        return True
    return False


def _choose_formation_by_templates() -> int:
    """在已打开的阵容选项界面，基于 formation_1/2/3 模板定位并点击第 formation_index 个阵容。
    返回实际点击的阵容索引（0..2），未找到时返回 -1。
    """
    formation_slots: list[tuple[int, int, int, int, int]] = []  # (idx, x, y, w, h)
    for i in range(1, 4):
        key = f'formation_{i}'
        path = TEMPLATES.get(key, '')
        if not path:
            continue
        matches = _find_all_template_matches(path, THRESHOLD)
        for (x, y, w, h) in matches:
            formation_slots.append((i - 1, x, y, w, h))
    if not formation_slots:
        return -1
    # 按纵向排序，越小的越靠上
    formation_slots.sort(key=lambda t: t[2])
    idx = formation_index if formation_index < len(formation_slots) else 0
    _, x, y, w, h = formation_slots[idx]
    _random_click_at(x, y, w, h)
    return formation_slots[idx][0]


def _click_formation(formation_idx: int) -> bool:
    key = f'formation_{formation_idx + 1}'
    path = TEMPLATES.get(key, '')
    if not path:
        return False
    found, loc, wh = _find_template_on_screen(path, THRESHOLD)
    if found:
        _random_click_at(loc[0], loc[1], wh[0], wh[1])
        time.sleep(random.uniform(0.5, 1.5))
        return True
    return False


def run():
    global formation_index
    print("[AutoMap] 进入推图循环。请确保玩家已手动进入关卡。按 Ctrl+C 结束脚本。")
    try:
        while True:
            try:
                # 暂停检查
                if 'PAUSED' in globals() and PAUSED:
                    time.sleep(0.5)
                    continue
                # 状态检测顺序：自动战斗结束 -> 失败/再次挑战 -> 其他(推图中)
                # 状态3: 自动战斗结束后点空白处并尝试再次挑战
                if _find_template_on_screen(TEMPLATES['auto_battle_end'], _template_threshold(TEMPLATES['auto_battle_end']))[0]:
                    print("[State 3] 自动战斗结束，关闭提示并尝试重新挑战。")
                    _click_random_blank_area()
                    time.sleep(random.uniform(1.0, 2.0))
                    _click_template('retry')
                    # 进入战前，尝试点击通关阵容并选择阵容
                    _click_template('formation_btn')
                    chosen = _choose_formation_by_templates()
                    if chosen >= 0:
                        formation_index = (chosen + 1) % MAX_FORMATIONS
                    else:
                        formation_index = 0
                    if _click_template('one_key_use'):
                        print(f"[State 3] 使用阵容成功，进到自动挑战。formation_index={formation_index}")
                    if _click_template('auto_challenge'):
                        print("[State 3] 已启动自动挑战")
                    time.sleep(random.uniform(0.5, 1.5))
                    # 已在上面更新 formation_index
                    time.sleep(random.uniform(0.5, 1.5))
                    continue

                # 状态2: 挑战失败 / 再次挑战
                failed = _find_template_on_screen(TEMPLATES['challenge_failed'], _template_threshold(TEMPLATES['challenge_failed']))[0]
                retry = _find_template_on_screen(TEMPLATES['retry'], _template_threshold(TEMPLATES['retry']))[0]
                if failed or retry:
                    print("[State 2] 识别到失败或再次挑战按钮，执行重试流程。")
                    if _click_template('retry'):
                        print("[State 2] 点击 再次挑战")
                    # 进入战前界面后，点击通关阵容
                    _click_template('formation_btn')
                    chosen = _choose_formation_by_templates()
                    if chosen >= 0:
                        formation_index = (chosen + 1) % MAX_FORMATIONS
                        print(f"[State 2] 选择阵容 index={chosen}")
                    else:
                        formation_index = 0
                        print("[State 2] 未找到阵容按钮，已重置 formation_index")
                    _click_template('one_key_use')
                    _click_template('auto_challenge')
                    time.sleep(random.uniform(0.5, 1.5))
                    # 继续保持 formation_index 的循环约束
                    formation_index = formation_index % MAX_FORMATIONS
                    print(f"[State 2] 更新 formation_index -> {formation_index}")
                    time.sleep(random.uniform(0.5, 1.5))
                    continue

                # 状态1: 推图成功/挂机状态，什么也不做，保持监控
                # 为了降低 CPU 占用，短暂休眠
                time.sleep(random.uniform(0.6, 1.2))

            except Exception as e:
                # 全局容错，确保脚本不会因个别错误崩溃
                print(f"[Error] 运行循环异常: {e}")
                time.sleep(random.uniform(0.5, 1.5))
                continue
    except KeyboardInterrupt:
        print("[AutoMap] 手动停止")
        return


if __name__ == '__main__':
    run()
