// pages/social/social.js —— 校园社交（演示版静态数据，正式版接云数据库）
Page({
  data: {
    rank: [
      { medal: '🥇', name: '林同学', cups: 32, streak: 7, me: false },
      { medal: '🥈', name: '陈同学', cups: 29, streak: 6, me: false },
      { medal: '🥉', name: '我', cups: 24, streak: 4, me: true },
      { medal: '4', name: '王同学', cups: 21, streak: 3, me: false },
      { medal: '5', name: '李同学', cups: 18, streak: 2, me: false }
    ],
    medals: [
      { icon: '🥤', name: '初来乍到', desc: '打卡第1天', got: true },
      { icon: '🔥', name: '三日坚持', desc: '连续3天', got: true },
      { icon: '💧', name: '补水达人', desc: '单日满6杯', got: true },
      { icon: '🏅', name: '七日连续', desc: '差3天解锁', got: false },
      { icon: '🌙', name: '晚自习之星', desc: '未解锁', got: false },
      { icon: '🎓', name: '考试周稳水', desc: '未解锁', got: false }
    ],
    feed: [
      { initial: '林', name: '林同学', text: '连续第7天达标，"稳住就是赢"', time: '10分钟前', like: 12, me: false },
      { initial: '我', name: '我', text: '今天第3杯，继续加油', time: '半小时前', like: 5, me: true },
      { initial: '陈', name: '陈同学', text: '运动后补了一杯，别猛灌哦', time: '1小时前', like: 8, me: false },
      { initial: '王', name: '王同学', text: '被搭子催来喝水了 😂', time: '2小时前', like: 21, me: false }
    ]
  },
  poke() {
    wx.showToast({ title: '已戳搭子：来一杯～', icon: 'none' });
  }
});
