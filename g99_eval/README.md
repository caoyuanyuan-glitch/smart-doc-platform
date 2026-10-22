# g99_eval

本目录 JSON（`old_goldset_rerun.json`、`ab_result.json`）是评测生成物，路径一律相对仓库根目录。

重新生成旧 goldset 状态：

```bash
SDP_ROOT=<repo> SDP_BACKEND=<repo>/backend python3 g99_eval/rerun_old_goldsets.py
```
