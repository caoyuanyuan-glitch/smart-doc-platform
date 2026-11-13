"""backend/scripts 包声明。

显式声明为常规包（而非 PEP 420 隐式命名空间包）：
- `python -m pytest` 会把 cwd 注入 sys.path[0]，`from scripts import ...` 可用；
- 直接调 `pytest` 可执行文件时 cwd 不进 sys.path，隐式命名空间包会 ModuleNotFoundError。
显式 __init__.py 不改变正常导入路径，但让包边界清晰、避免后续新增子包时行为不一致。
"""
