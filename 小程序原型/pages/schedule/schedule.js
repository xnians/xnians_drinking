// pages/schedule/schedule.js —— 课表联动（演示版固定时段，正式版导入真实课表）
const raw = [
  { s:7, e:8, scene:'早八出门', sub:'宿舍 → 教室', lines:{
    xueba:'出门前花10秒灌满水，比课间跑回宿舍取划算得多。',
    tucao:'别等走到教学楼才想起没带水，顺手把水杯塞进书包。',
    shuijing:'主人～把我放进书包侧袋，我陪你去教室呀🥤' }},
  { s:9, e:10, scene:'课间10分钟', sub:'教室起身接水', lines:{
    xueba:'起身接杯水，顺便活动一下，下节课专注力更稳。',
    tucao:'坐一上午了，水杯是落宿舍了吗？站起来去接水。',
    shuijing:'课间啦，给我续点水嘛，我想陪你上下一节课💧' }},
  { s:10, e:12, scene:'自习/上课50分钟', sub:'专注后补水', lines:{
    xueba:'专注50分钟记得补一口，水分够，记忆力才在线。',
    tucao:'别硬撑到嗓子冒烟，先喝口水再继续卷。',
    shuijing:'学累啦？喝一口水，我给你加油✨' }},
  { s:12, e:13, scene:'食堂就餐', sub:'饭前温水', lines:{
    xueba:'饭前先喝口温水，别用甜饮料代替正餐补水。',
    tucao:'又想拿可乐下饭？先喝口白水，别糊弄肚子。',
    shuijing:'吃饭前喝口温水，肠胃会舒服一点哦🍚' }},
  { s:16, e:18, scene:'运动后', sub:'操场/体育课', lines:{
    xueba:'运动后小口多次补水，别一次性猛灌。',
    tucao:'大汗淋漓别对着瓶子猛灌，小口喝，温水最好。',
    shuijing:'运动完慢慢喝，我陪你慢慢恢复呀💙' }},
  { s:19, e:21, scene:'晚自习', sub:'傍晚到夜间', lines:{
    xueba:'晚自习别靠咖啡硬顶，累了先补水+短暂休息。',
    tucao:'别拿奶茶当水喝，晚自习也得喝真水。',
    shuijing:'晚自习辛苦啦，喝口水我们继续✨' }},
  { s:23, e:24, scene:'睡前', sub:'宿舍润喉', lines:{
    xueba:'睡前小口润喉，顺手把明早的水杯备好。',
    tucao:'别灌一大杯撑着睡，抿两口就行，明早的水先备好。',
    shuijing:'晚安前喝一小口，我在桌上等你明天🥺' }},
  { s:0, e:24, scene:'考试周全天', sub:'规律补水稳状态', lines:{
    xueba:'考试周规律补水、睡够，状态稳定比突击更重要。',
    tucao:'考前慌也没用，喝口水，一道一道刷，别熬废身体。',
    shuijing:'考试加油！一口一口喝水，一题一题来💪' }}
];
const pad = n => String(n).padStart(2,'0');

Page({
  data: { role: 'xueba', slots: [], nowText: '' },
  onShow() {
    const role = wx.getStorageSync('role') || 'xueba';
    const nowH = new Date().getHours();
    const slots = raw.map(it => ({
      ...it,
      range: it.s === 0 ? '全天' : `${pad(it.s)}:00–${pad(it.e)}:00`,
      now: (it.s === 0 && it.e === 24) || (nowH >= it.s && nowH < it.e),
      open: false
    }));
    const cur = slots.find(it => it.now);
    const nowText = cur
      ? `🔔 现在是「${cur.scene}」时段：${cur.lines[role]}`
      : '现在还没有到提醒节点，先看看下面的时段表～';
    this.setData({ role, slots, nowText });
  },
  toggle(e) {
    const i = e.currentTarget.dataset.index;
    const slots = this.data.slots.map((it, idx) => idx === i ? { ...it, open: !it.open } : it);
    this.setData({ slots });
  }
});
