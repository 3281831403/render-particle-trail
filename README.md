# render-particle-trail

## 题面

给技能加拖尾后，角色一瞬移拖尾就连成一根长棍：历史帧不设上限，长时间运行内存线性增长；位移过大时不断开，拖尾被连成一条折线；淡出方向写反，头部透明度为 0 而尾端最亮；条带相邻段法线不连续，弯曲处出现折痕；静止时重复点不去重，生成零面积面；按距离排序使用不稳定排序，重叠片段闪烁；历史长度超过 max_len 不报错，直接越界；位置含 NaN 不校验，条带渲染成黑色；批量构建共用同一个历史队列，多个发射器拖尾互相串线；max_len=0 不校验，后续计算除零崩溃。trail/history.py 是核心，tests/test_history.py 15个红。要修的是：历史帧数上限、瞬移断开、淡出方向、法线连续、静止去重、稳定排序、长度校验、NaN 校验、批量隔离和 max_len 零值校验。

## 运行方式

在仓库根目录执行：

```powershell
python -m pytest tests -q
```

初始状态下输出尾部应为 `15 failed`（例如 `15 failed in 0.12s`），且不得出现 collection error、import error 或 syntax error。15 个测试全部先因桩函数抛出 `NotImplementedError` 而变红。

## 字段表

| 字段 | 取值 |
| --- | --- |
| 所属领域 | 游戏、图形与多媒体 |
| 子方向 | 图形渲染 |
| 任务类型 | Bugfix |
| 语言/框架 | Python 3, pytest |
| 环境可复现等级 | 无外部依赖 |

## 数据与实现约定

- 只用 Python 标准库（`math`、`collections`）和 pytest；离线运行，不使用随机数。
- 世界坐标为米；浮点比较的绝对容差为 `1e-6`。
- 输入粒子为 `{"id", "pos", "alive"}`；历史按“最老帧在前、最新帧在后”排列，每帧是 `{粒子 id: (x, y)}` 的活粒子快照。
- 八个待实现函数都在 `trail/history.py`，异常统一使用 `TrailError`。

## 测试约束

`tests/test_history.py` 是评测基准，不可修改；不得删除、跳过、改写或放宽任何测试。修复只能落在实现代码中。
