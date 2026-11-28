// pages/social/social.js —— 校园社交：榜单 / 勋章 / 动态，均由本地打卡数据驱动（演示版，正式版接云数据库）
const GOAL = 6;
const STORE_KEY = 'kd_state_v1';

const CLASSMATES = [
  { name: '林同学', base: 32, streak: 7 },
  { name: '陈同学', base: 29, streak: 6 },
  { name: '王同学', base: 21, streak: 3 },
  { name: '李同学', base: 18, streak: 2 }
];

const DEFAULT_FEED = [
  { initial: '林', name: '林同学', text: '连续第7天达标，"稳住就是赢"', time: '10分钟前', like: 12, me: false },
  { initial: '陈', name: '陈同学', text: '运动后补了一杯，别猛灌哦', time: '1小时前', like: 8, me: false },
  { initial: '王', name: '王同学', text: '被搭子催来喝水了 😂', time: '2小时前', like: 21, me: false }
];

function dateStr(d){
  d = d || new Date();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${m}-${day}`;
}

Page({
  data: { rank: [], rankTip: '', medals: [], feed: [] },

  onShow(){
    this.state = this.loadState();
    this.render();
  },

  loadState(){
    let s = { date: dateStr(), cups: 0, logs: [], streak: 0, metToday: false,
              evening: false, history: {}, role: 'xueba', feed: [] };
    try {
      const raw = wx.getStorageSync(STORE_KEY);
      if(raw){ s = Object.assign(s, JSON.parse(raw)); }
    } catch(e){}
    s.history = s.history || {};
    s.feed = s.feed || [];
    return s;
  },

  save(){
    try { wx.setStorageSync(STORE_KEY, this.state); } catch(e){}
  },

  weekList(){
    const out = [];
    const today = new Date();
    for(let i = 6; i >= 0; i--){
      const d = new Date(today); d.setDate(today.getDate() - i);
      const key = dateStr(d);
      out.push(i === 0 ? this.state.cups : (this.state.history[key] || 0));
    }
    return out;
  },

  render(){
    // 榜单：其他同学为演示基线，"我"的杯数取近7天本地打卡累加，合并排序后自己高亮
    const myWeek = this.weekList().reduce((a, b) => a + b, 0);
    const rows = CLASSMATES.map(c => ({ name: c.name, cups: c.base, streak: c.streak, me: false }));
    rows.push({ name: '我', cups: myWeek, streak: this.state.streak, me: true });
    rows.sort((a, b) => b.cups - a.cups);
    const medals = ['🥇', '🥈', '🥉'];
    rows.forEach((r, i) => { r.medal = medals[i] || String(i + 1); });
    const meRank = rows.findIndex(r => r.me) + 1;
    const rankTip = meRank <= 1
      ? '你已经排在最前面啦，继续稳住 💪'
      : `你目前排第 ${meRank} 名，前面那位别让他跑太远，再补两杯就追上去 💪`;

    // 勋章：按真实行为点亮 / 置灰
    const week = this.weekList();
    const daysCheckedIn = week.filter(c => c > 0).length;
    const weekMet = week.filter(c => c >= GOAL).length;
    const medalList = [
      { icon: '🥤', name: '初来乍到', desc: daysCheckedIn >= 1 ? '已打卡' : '打卡第1天', got: daysCheckedIn >= 1 },
      { icon: '🔥', name: '三日坚持', desc: '连续3天', got: this.state.streak >= 3 },
      { icon: '💧', name: '补水达人', desc: this.state.cups >= GOAL ? '今日满6杯' : '单日满6杯', got: this.state.cups >= GOAL },
      { icon: '🏅', name: '七日连续', desc: '连续7天', got: this.state.streak >= 7 },
      { icon: '🌙', name: '晚自习之星', desc: this.state.evening ? '晚间已打卡' : '晚自习打卡', got: this.state.evening },
      { icon: '🎓', name: '考试周稳水', desc: '近7天5天达标', got: weekMet >= 5 }
    ];

    // 动态流：本地产生的动态 + 默认演示动态
    const feed = [...this.state.feed, ...DEFAULT_FEED];

    this.setData({ rank: rows, rankTip, medals: medalList, feed });
  },

  // 提醒搭子喝水：产生一条本地动态
  poke(){
    this.state.feed.unshift({
      initial: '我', name: '我',
      text: '提醒了搭子来喝水："水还没喝哦，来一杯～"',
      time: '刚刚', like: 0, me: true
    });
    this.save();
    this.render();
    wx.showToast({ title: '已戳搭子：来一杯～', icon: 'none' });
  }
});
