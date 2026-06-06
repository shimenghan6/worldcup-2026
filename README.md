# 🏆 2026 世界杯赛程日历 | World Cup 2026 Schedule

> 48队 · 104场 · 实时倒计时 · AI投注分析 · 北京时间

**🔗 在线访问**: https://你的用户名.github.io/worldcup-2026

---

## ✨ 功能

- 📅 **完整赛程** — 小组赛48场全收录，北京时间，场地信息
- 🔴 **今日比赛** — 自动高亮当天场次 + 预览下一比赛日
- 📊 **分组积分** — 12组48队一览，晋级形势可视化
- ⭐ **焦点战** — 梅西/C罗谢幕战、死亡之组、强强对话
- 🤖 **AI分析** — 每场SPF赔率+推荐结果+信心等级
- ⏱️ **揭幕战倒计时** — 实时更新
- 📱 **响应式** — 手机/平板/桌面全适配
- 🎨 **世界杯主题** — 暗色高级感设计

## 🚀 一键部署

### GitHub Pages（免费）

```bash
# 1. Fork 或创建仓库
# 2. 上传所有文件
# 3. Settings → Pages → Source: main branch → Save
# 4. 等1分钟就上线了
```

### 本地预览

```bash
# 任意HTTP服务器即可
npx serve .
# 或
python -m http.server 8080
```

## 🤖 自动化数据更新

```
🐍 Python每小时 → 自动启动浏览器 → 抓取竞彩网赔率 → git push
🧠 Claude每天8:03 → 搜索伤病情报 → 重新评估预测 → 校验 → git push
                     ↓
            GitHub Pages 自动部署
```

### 一键安装（Windows）

双击 `setup_scheduler.bat` →
- 自动安装依赖
- 创建每小时定时任务
- 浏览器自动启动(支持Chrome/Edge)，无需手动操作

### 手动运行

```bash
python fetch_odds.py              # 全自动抓取+更新+推送
python fetch_odds.py --headless   # 无窗口模式(后台静默运行)
python fetch_odds.py --dry-run    # 仅测试不推送
```

## 🤖 AI分析引擎

配套 [lottery-analyzer](https://github.com) skill：

- 搜索球队伤病/阵容/状态
- 生成每场全玩法（SPF+让球+总进球+半全场+比分）分析
- 输出500/1000元两档投注方案

## 📊 数据来源

- 赛程数据：FIFA官方 + 权威体育媒体
- 赔率数据：中国竞彩网 (sporttery.cn)
- 球队情报：公开体育媒体
- 分析引擎：Claude AI

## ⚠️ 声明

- 赔率为国际盘口换算预估，实际以竞彩出票为准
- 不构成投注建议，仅供分析参考
- 唯一合法购彩渠道：中国体育彩票线下实体店（95086）
- 禁止未成年人购彩
- 理性购彩，量力而行

## 📄 License

MIT
