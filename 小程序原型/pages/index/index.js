// pages/index/index.js —— 首页逻辑
const talks = {
  xueba: [
    '早八先喝一杯温水，大脑开机更快。',
    '自习50分钟记得补一口，专注力会回来。',
    '今天已经喝了{cups}杯，保持节奏，别断档。',
    '水分充足，记忆力和状态都会在线。'
  ],
  tucao: [
    '又想靠奶茶续命？先把这杯温水喝了再说。',
    '你都坐一上午了，水杯是落宿舍了吗？',
    '别等嗓子冒烟才想起来喝水，那是透支。',
    '{cups}杯了，再坚持一下，别半途而废啊。'
  ],
  shuijing: [
    '咕嘟咕嘟～喝一口水，我就变圆一点点🥺',
    '宝宝，水杯就在手边，抬抬手就喝啦💧',
    '已经{cups}杯啦，你对我真好，么么哒✨',
    '不喝水我会蔫掉的，快喂我一口嘛～'
  ]
};
const roleName = { xueba: '学霸同桌', tucao: '吐槽搭子', shuijing: '软萌水精灵' };

Page({
  data: {
    goal: 6,
    cups: 0,
    percent: 0,
    role: 'xueba',
    roleName: '学霸同桌',
    talk: '',
    roles: [
      { key: 'xueba', name: '学霸同桌' },
      { key: 'tucao', name: '吐槽搭子' },
      { key: 'shuijing', name: '软萌水精灵' }
    ],
    logs: [],
    dateStr: ''
  },

  onLoad() {
    const d = new Date();
    const week = ['周日','周一','周二','周三','周四','周五','周六'][d.getDay()];
    this.setData({ dateStr: `${d.getMonth()+1}月${d.getDate()}日 ${week}` });
    this.say();
  },

  // 随机说一句当前人设的话
  say() {
    const arr = talks[this.data.role];
    let t = arr[Math.floor(Math.random() * arr.length)];
    t = t.replace('{cups}', this.data.cups);
    this.setData({ talk: t, roleName: roleName[this.data.role] });
  },

  switchRole(e) {
    this.setData({ role: e.currentTarget.dataset.key });
    this.say();
  },

  drink() {
    if (this.data.cups >= this.data.goal) { this.say(); return; }
    const cups = this.data.cups + 1;
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, '0');
    const mm = String(now.getMinutes()).padStart(2, '0');
    const logs = [{ cup: cups, time: `${hh}:${mm}` }, ...this.data.logs];
    this.setData({
      cups,
      percent: Math.round(cups / this.data.goal * 100),
      logs
    });
    this.say();
  }
});
