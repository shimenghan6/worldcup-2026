// 数据一致性校验脚本 - 每次 data.json 更新后必须运行
// 用法: node validate-data.js
const fs = require('fs');

const data = JSON.parse(fs.readFileSync('data.json', 'utf8'));
const errors = [];

for (const m of data.matches) {
  const {id, tip, score, htft} = m;
  if (tip === '待定' || !score || !htft) continue;

  const parts = (score || '').split('/')[0].split(':');
  if (parts.length < 2) continue;
  const [h, g] = parts.map(Number);
  if (isNaN(h) || isNaN(g)) continue;

  // 铁律: tip=胜 → 主队赢 → 比分主>客 (h > g)
  if (tip === '胜' && h <= g)
    errors.push({id, issue: 'tip=胜(主胜)但比分主队≤客队', tip, score});

  // 铁律: tip=负 → 客队赢 → 比分主<客 (h < g)
  if (tip === '负' && h >= g)
    errors.push({id, issue: 'tip=负(客胜)但比分主队≥客队', tip, score});

  // 铁律: tip=平 → 比分相等
  if (tip === '平' && h !== g)
    errors.push({id, issue: 'tip=平但比分不平', tip, score});

  // 铁律: tip=胜 → 半全场不能是客胜模式
  if (tip === '胜' && /负.负|平.负|负.平/.test(htft))
    errors.push({id, issue: 'tip=胜但半全场显示客胜', tip, htft});

  // 铁律: tip=负 → 半全场不能是主胜模式
  if (tip === '负' && /胜.胜|胜.平|平.胜/.test(htft))
    errors.push({id, issue: 'tip=负但半全场显示主胜', tip, htft});
}

if (errors.length > 0) {
  console.log(`❌ 发现 ${errors.length} 处数据矛盾:`);
  errors.forEach(e => console.log(`  ID#${e.id}: ${e.issue} | tip=${e.tip} | ${e.score||e.htft}`));
  process.exit(1);
}

console.log(`✅ 全部 ${data.matches.length} 场数据一致性校验通过`);
