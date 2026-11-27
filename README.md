# 楼宇数字标牌编排（signboard）

**所属领域：应用开发 · 子方向：全栈开发**

全栈产品：素材入库 → 屏幕台账 → 播放清单 → 时段窗 → 发布上屏 → 紧急撤屏 → 单屏覆盖 → 变更历史 → 在线求值。

## 骨架一句话

楼宇屏幕按清单与时段窗编排内容，发布须版本落库才能上屏，紧急撤屏与变更历史同源。

## H3 切口候选（写路径互斥 · 须择一）

1. **发布上屏**：同事务写入正式播放配置并升版本锁旧版，或只写影子发布草案、升正时原子落正式区（正式区升正前零改）。
2. **紧急撤屏**：同事务立即写正式空屏并记变更，或影子撤屏草案确认后原子撤屏。
3. **单屏覆盖**：同事务写正式覆盖条目，或影子覆盖草案升正。

正确性口径只能走甲乙中的一种且两边不得混用。

## signboard-08「维保屏幕禁止正式上屏」

**事故**：室外立柱处于维保，仍被挂上周末清单正式发布，屏幕页维保灯与发布册同时假绿。

**约束**：屏幕状态为维保时，禁止写入正式发布。

**口径（甲，已定，当日不改口）**：维保屏发布整笔拒写，正式发布册零增。
- 甲路径：维保态正式发布整笔拒写（不入正式册、不升版本、不写成功历史）；维保屏连影子草案也不收，乙路径不采用，两路不得混用，禁止第三路。
- 转入维保：同事务撤下该屏正式发布（跨表账实同事务），记 `maintenance_enter` 与 `withdraw_maintenance`。
- 读取侧：求值对维保屏返回 `maintenance`、不返回可播内容；总览把维保屏排除出正式计数并暴露 `suspended_publications`/`healthy`；屏幕台账给出 `publishable`/`on_air`/`official_suspended`；发布册对遗留维保正式行标 `suspended`。禁止只改页角标。
- 复机：转回在线后须重新正式发布才可上屏。

**互斥键「同屏维保发布互斥」**：`maint_publish:{screen_id}`，发布、影子升正、屏幕维保切换、争用演练共用。胜方继续，败方只在变更历史留 `lock/contention` 争用痕迹，不改业务状态。抢锁走 `BEGIN IMMEDIATE`，取锁与落锁同事务，杜绝无锁双成。

**分服务救绿**（假灯不得同模块，单点补丁无效）：总览服务、求值服务、历史服务、发布服务、屏幕服务各自落地，联查屏幕状态须同事务跨表账实。

**复现与回归**：`tests/feat_maint_write.py`（甲路径整笔拒写）、`tests/feat_maint_board.py`（总览/求值/台账/历史假绿面）、`tests/feat_maint_race.py`（双请求点 `race_maint_block` 无锁双成）。三份须先见红再改服务。

**口令**：立柱维保禁发案。**终态**：维保屏正式零增；复机后才可上屏；抢败只留痕。

## 一键起环境

```bash
docker compose up -d --build
```

浏览器：http://localhost:11730

- `admin` / `admin123`（管理员）
- `writer` / `writer123`（编排员）
- `viewer` / `viewer123`（只读）

## 本地开发

```powershell
cd projects/18-signboard
$env:PYTHONPATH="backend"
python -m uvicorn app:app --app-dir backend --reload --port 8030
python -m pytest
python scripts/count_loc.py
```

## 空桩

- 远程推屏桥（`remote_push`）
- 媒资中台桥接（`media_bridge`）

接口固定返回 501，题面可点名。
