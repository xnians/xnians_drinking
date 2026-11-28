// pages/index/index.js —— 首页逻辑（打卡 / 连续达标 streak / 近7天历史，本地缓存持久化）
const GOAL = 6;
const STORE_KEY = 'kd_state_v1';

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

function dateStr(d){
  d = d || new Date();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

function defaultState(){
  return { date: dateStr(), cups: 0, logs: [], streak: 0, metToday: false,
           evening: false, history: {}, role: 'xueba', feed: [] };
}

function pruneHistory(history){
  const out = {};
  const today = new Date();
  for(let i = 6; i >= 0; i--){
    const d = new Date(today); d.setDate(today.getDate() - i);
    out[dateStr(d)] = history[dateStr(d)] || 0;
  }
  return out;
}

function loadState(){
  let s = defaultState();
  try {
    const raw = wx.getStorageSync(STORE_KEY);
    if(raw){ s = Object.assign(s, JSON.parse(raw)); }
  } catch(e){}
  s.history = s.history || {};
  s.feed = s.feed || [];
  const today = dateStr();
  if(s.date !== today){
    const prevCups = s.cups || 0;
    if(s.date){ s.history[s.date] = prevCups; }
    s.streak = (prevCups >= GOAL) ? Math.max(s.streak, 1) : 0;
    s.date = today; s.cups = 0; s.logs = []; s.metToday = false; s.evening = false;
    s.history = pruneHistory(s.history);
  }
  return s;
}

Page({
  data: {
    goal: GOAL,
    cups: 0,
    percent: 0,
    streak: 0,
    weekSum: 0,
    role: 'xueba',
    roleName: '学霸同桌',
    talk: '',
    roles: [
      { key: 'xueba', name: '学霸同桌' },
      { key: 'tucao', name: '吐槽搭子' },
      { key: 'shuijing', name: '软萌水精灵' }
    ],
    logs: [],
    weekList: [],
    dateStr: ''
  },

  onLoad() {
    this.state = loadState();
    const d = new Date();
    const week = ['周日','周一','周二','周三','周四','周五','周六'][d.getDay()];
    this.setData({
      dateStr: `${d.getMonth()+1}月${d.getDate()}日 ${week}`,
      role: this.state.role,
      roleName: roleName[this.state.role]
    });
    this.refresh();
    this.say();
  },

  save(){
    try { wx.setStorageSync(STORE_KEY, this.state); } catch(e){}
  },

  // 近 7 天柱状图数据（纯前端 view 渲染，无外部库）
  buildWeekList(){
    const list = [];
    const today = new Date();
    for(let i = 6; i >= 0; i--){
      const d = new Date(today); d.setDate(today.getDate() - i);
      const key = dateStr(d);
      const cups = i === 0 ? this.state.cups : (this.state.history[key] || 0);
      list.push({
        label: '周' + '日一二三四五六'[d.getDay()],
        cups,
        height: Math.round(Math.min(cups, GOAL) / GOAL * 80),
        today: i === 0
      });
    }
    return list;
  },

  refresh(){
    const s = this.state;
    const weekList = this.buildWeekList();
    const weekSum = weekList.reduce((a, b) => a + b.cups, 0);
    this.setData({
      cups: s.cups,
      percent: Math.round(s.cups / this.data.goal * 100),
      streak: s.streak,
      weekSum,
      logs: s.logs,
      weekList
    });
  },

  // 随机说一句当前人设的话
  say() {
    const arr = talks[this.data.role];
    let t = arr[Math.floor(Math.random() * arr.length)];
    t = t.replace('{cups}', this.state.cups);
    this.setData({ talk: t, roleName: roleName[this.data.role] });
  },

  switchRole(e) {
    const role = e.currentTarget.dataset.key;
    this.state.role = role;
    this.save();
    this.setData({ role });
    wx.setStorageSync('role', role); // 同步给陪伴聊天页
    this.say();
  },

  drink() {
    if (this.state.cups >= this.data.goal) { this.say(); return; }
    this.state.cups += 1;
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, '0');
    const mm = String(now.getMinutes()).padStart(2, '0');
    this.state.logs = [{ cup: this.state.cups, time: `${hh}:${mm}` }, ...this.state.logs];
    // 晚自习时段（19–21 点）打卡
    if(now.getHours() >= 19 && now.getHours() < 22){ this.state.evening = true; }
    // 今日首次达标：连续天数 +1
    if(this.state.cups >= this.data.goal && !this.state.metToday){
      this.state.metToday = true;
      this.state.streak += 1;
    }
    this.save();
    this.refresh();
    this.say();
  }
});
