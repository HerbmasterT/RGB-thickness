# hBN 光学对比度拟合

本项目仅保留光学对比度拟合程序，用于尝试 hBN / 约 285 nm SiO₂ / Si 反射图像、约 0–30 nm 厚度范围的经验标定。

## 启动

Windows 下双击根目录的 `start.bat`，或 `optical_contrast/start.bat`，均启动同一个程序。

其他环境需要 Python 3.10+、Tkinter 和 Pillow。在项目根目录运行：

```powershell
python -m pip install -r requirements.txt
python optical_contrast/optical_contrast_inspector.py
```

## 使用

1. 打开本地图片，用 **background** 选取裸衬底区域，用 **signal** 选取样品区域。支持单点和矩形采样。
2. 点击“加入拟合”，填写 AFM 测得的厚度（nm），勾选参与拟合的行。
3. 选择 C_G（默认）、C_B 或 C_R，进行线性拟合，查看斜率、截距、R²、训练 RMSE 和残差图。
4. 返回“图片分析”页，选择待测区域并点击“厚度计算”，显示预测厚度（nm）以及使用的拟合通道。
5. 使用 TXT 导入、导出保存表格。

对比度为 `C_X = (背景区域通道均值 - 样品区域通道均值) / 背景区域通道均值`，保留正负号。计算使用图片已有的 0–255 通道编码值；结果属于固定成像条件下的经验标定，真实厚度预测精度需要独立实验验证。

详细的采样方式、计算假设、数据格式和测试方法见 [使用说明](optical_contrast/README.md)。

## 项目结构与数据

- `optical_contrast/`：唯一的程序版本、依赖清单和测试。
- `start.bat`、`requirements.txt`：根目录的启动和安装入口。
- `AGENTS.md`：长期工作约定，每次修改后验证、提交并同步到 GitHub。
- 本地实验图片和导出结果可保存在根目录 `data/`、`results/`；这些目录、现有测量表和缓存不纳入版本管理。

原 HSV 和色差版本已从当前项目删除，历史代码仍可通过 Git 提交记录查阅。本地已有测量数据保留；旧 RGB 表或色差表不能直接导入光学对比度版本。

## 验证

在 `optical_contrast` 目录运行：

```powershell
python -m unittest discover -s tests -v
python tests/gui_workflow.py
python tests/gui_thickness.py
```

测试使用合成数据；GUI 测试需要可用的桌面显示环境。
