# 自动推图脚本（PC 端游戏）

基于屏幕截图与模板匹配实现的自动推图脚本，使用 OpenCV、MSS、PyDirectInput，并通过简单的状态机完成“推图/失败再战/自动战斗结束”的自动化场景。

## 功能概览
- MSS 高效抓取屏幕
- OpenCV 模板匹配，默认置信阈值 0.85（可对单模板设定单独阈值）
- PyDirectInput 点击，带随机偏移与随机延时，降低被检测的风险
- 阵容选择通过两个阶段实现：点击“通关阵容”按钮后，基于 formation_1.png、formation_2.png、formation_3.png 识别并点击第一个可用阵容（按纵向排序），最多轮换 3 个阵容
- 状态机分为三类：状态1 推图中/挂机、状态2 挑战失败/再次挑战、状态3 自动战斗结束
- 产出日志 auto_map_game.log，同时输出到控制台

## 依赖与环境
- Python 3.x
- Windows 系统（脚本在 Windows 下测试通过）
- 依赖安装：
  ```bash
  pip install mss opencv-python numpy pydirectinput
  ```
- 可选：若要使用暂停热键，需要安装 keyboard：
  ```bash
  pip install keyboard
  ```

## 目录结构与资源
- auto_map_game.py  // 主脚本
- templates/        // 模板图片目录（可放置你提供的图片）
- auto_map_game.log  // 运行日志（首次运行后生成）
- README.md          // 本文件

模板图片的命名（脚本会加载同名图片，若你把图片放在 templates/ 下，请确保名称一致）
- formation_btn.png      // 通关阵容按钮
- formation_1.png、formation_2.png、formation_3.png  // 三个阵容模板
- auto_challenge.png     // 自动挑战按钮
- retry.png              // 再次挑战
- one_key_use.png         // 一键采用
- challenge_failed.png   // 挑战失败提示
- auto_battle_end.png    // 自动战斗结束提示

注：脚本会优先从脚本所在目录加载模板图片，若找不到，会回退到 templates/ 子目录。

## 使用前提
- 玩家的初始条件：玩家已经手动进入关卡，脚本启动后进入循环监控。
- 确保目标游戏在前台，分辨率稳定，以便模板匹配正常工作。

## 运行步骤
## 配置与自定义（高级）
- 阈值控制：全局阈值 THRESHOLD = 0.85；不同模板可通过 THRESHOLD_MAP 调整，键为图片文件名（如 "formation_btn.png"）的基名。
- 阵容轮换：formation_index 控制当前使用的阵容顺序，最多轮换 3 个阵容。
- 模板组织：脚本支持自动从模板根目录或 templates/ 目录加载图片，便于扩展与维护。
- 打开阵容界面后，脚本会基于 formation_1.png、formation_2.png、formation_3.png 逐个匹配，找到所有符合条件的阵容项并按纵向排序选择第 formation_index 个。

## 日志与可观测性
- 日志输出到 auto_map_game.log，以及控制台输出关键事件（进入状态、选中阵容、启动自动挑战等）。

## 常见问题与排查
- 模板识别失败：请确保提供的模板图片与当前分辨率一致，必要时重新截取并替换模板图片。
- 屏幕缩放/分辨率不同导致识别失败：可尝试为脚本运行的游戏使用固定分辨率的桌面，或提供多尺度模板。
- 若未安装 keyboard 库，请移除热键相关代码；脚本将以默认模式继续运行。

## 版本与变更记录
- 未来可通过 README 更新版本说明和新增的模板/机制。

## 许可
- 本脚本仅用于个人学习与测试用途，请遵守应用商店/游戏厂商的相关规定。
