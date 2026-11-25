// app.js —— 小程序全局逻辑（这里先放基础配置）
App({
  globalData: {
    goal: 6,          // 今日目标杯数
    cups: 0           // 已喝杯数
  },
  onLaunch() {
    // 小程序启动时执行，预留：可从本地读取上次记录
  }
});
