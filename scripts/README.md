# 数据自动更新 · 使用说明

`fetch_data.py` 每周自动抓取公开榜单数据，更新 `data/models.json`，并由 GitHub
Actions 自动部署到 GitHub Pages——全流程零人工维护。

## 数据源（均为公开接口）

| 数据源 | 接口 | 更新字段 |
| --- | --- | --- |
| LMArena（全球人类盲测 Elo） | HuggingFace 数据集 `lmarena-ai/leaderboard-dataset` | `elo` |
| SuperCLUE 智能指数（中文能力） | `superclueai.com/data/generalboard/<月份>.xlsx` | `superclue` |
| SuperCLUE 价格（官方标价） | `superclueai.com/data/latency_and_price/<月份>_2.xlsx` | `priceIn` / `priceOut` |

> 注意：HuggingFace 在国内网络环境下可能无法直接访问，但在 GitHub Actions
> （海外服务器）中可以正常抓取，无需任何配置。

## 容错设计

- 某个数据源抓取失败或匹配不到模型时，**自动保留旧值**，网站不会因此坏掉。
- 字段被权威来源更新后，自动移除该字段的「估算」标记。
- 每次运行生成变更摘要 `data/.last_update.json`，可在 GitHub Actions 日志中查看。

## 本地运行

```bash
python scripts/fetch_data.py            # 正式更新
python scripts/fetch_data.py --dry-run  # 预览变更，不写文件
```

## 接入 GitHub（一次性配置，约 5 分钟）

1. **新建仓库**：在 GitHub 上创建一个仓库（Public 或 Private 均可）。

2. **推送代码**（把本目录内容作为仓库根目录推送）：

   ```bash
   cd maas-rank
   git init
   git add -A
   git commit -m "feat: MaaS 模型排行网站"
   git branch -M main
   git remote add origin https://github.com/<你的用户名>/<仓库名>.git
   git push -u origin main
   ```

3. **开启 GitHub Pages**：仓库 Settings → Pages → Source 选择
   **GitHub Actions**，保存。首次部署后会自动生成站点地址
   `https://<你的用户名>.github.io/<仓库名>/`。

4. **确认工作流已启用**：仓库 Actions 页面应能看到
   `自动更新榜单数据并部署` 工作流。可以点 **Run workflow** 手动跑一次验证。

之后：**每周一 09:30（北京时间）** 工作流自动运行；若榜单数据有变化，会自动
提交并重新部署，无需任何操作。

## 手动触发

仓库 Actions → 选择工作流 → Run workflow（手动执行一次）。
