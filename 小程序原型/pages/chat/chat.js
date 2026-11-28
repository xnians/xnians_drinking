// pages/chat/chat.js —— AI 陪伴聊天（双路：联网走大模型；无 key / 失败 / 离线自动回退本地规则句库）

/* ===== 联网大模型配置（在这里填你的 API key）=====
 * 注意：这是演示直连写法，把 key 写在源码里不安全。
 * 微信小程序正式版需要在小程序后台配置 request 合法域名，
 * 并且应走后端代理转发请求，不要把 key 直接发给前端。 */
const API_BASE_URL = 'https://api.deepseek.com'; // OpenAI 兼容接口地址，默认 DeepSeek，可换成其他兼容服务
const API_KEY = ''; // 留空 = 不联网，直接走本地规则句库（在这里填你的 API key）
const MODEL = 'deepseek-chat';

// 三套人设 system prompt（按当前选中人设注入）
const SYSTEM_PROMPT = {
  xueba: '你是「学霸同桌」，理性靠谱的学习伙伴，从记忆效率、学习方法切入鼓励人。语气温和简短口语，结尾自然带一句喝水提醒；不要长篇大论。',
  tucao: '你是「吐槽搭子」，嘴硬心软、毒舌但暖心、带点梗，简短口语，吐槽完要给台阶，自然催喝水；不要真的伤人。',
  shuijing: '你是「软萌水精灵」，可爱撒娇、多用叠词和 emoji，软乎乎，简短口语，撒娇式催喝水。'
};

const reply = {
  xueba: {
    tired: ['累了就先停下来喝口水，把任务拆成小块，完成一块休息一下。','疲劳时硬撑效率很低，补水+短暂休息，比咬牙扛更划算。'],
    exam: ['考试焦虑很正常，先喝口水深呼吸，把要背的内容列成清单，一项一项来。','你已经准备了很久，现在稳住节奏，水喝够、觉睡够，发挥才稳。'],
    sad: ['我在听。情绪不好的时候先照顾身体，喝口水，慢慢说，不用急。','难过是暂时的，你愿意说出来就已经很勇敢了。'],
    hungry: ['别用零食顶，先喝口温水，正餐按时吃，身体才扛得住。'],
    thanks: ['不客气，照顾好自己比什么都重要。'],
    hello: ['你好呀，今天有什么想聊的？'],
    fallback: ['嗯，我在听。不管什么事，先喝口水，我们慢慢理一理。','收到。愿意多说说吗？我陪你一起想办法。']
  },
  tucao: {
    tired: ['累就对了，谁让你硬撑。先喝口水歇会儿，别把自己熬废了。','又累又不喝水，你这是跟自己过不去？坐下，喝水。'],
    exam: ['考前慌也没用，书又不会因为你焦虑自己跑进脑子。喝口水，一道一道刷。','别自己吓自己，你准备的够多了，先喝水，稳住。'],
    sad: ['咋了这是？先喝口水，天塌不下来，跟我说说。','行了行了，别憋着，喝口水，吐槽出来我听着。'],
    hungry: ['又想吃零食？先喝口白水，别拿甜的糊弄肚子。'],
    thanks: ['客气啥，记得喝水就行。'],
    hello: ['哟，来了，今天又想让我念叨你啥？'],
    fallback: ['行，我听见了。先喝口水，别一个人钻牛角尖。','嗯，说下去，我耳朵在。']
  },
  shuijing: {
    tired: ['辛苦啦抱抱🫂 先喝口水，歇一小会儿，我陪着你呀。','累了就靠一靠，喝口水，我们慢慢再来💙'],
    exam: ['别紧张别紧张，喝口水深呼吸，你可以的💪 我一直在桌边陪你。','考试加油！把害怕先放一放，一口一口喝水，一题一题来✨'],
    sad: ['呜呜，不开心就告诉我呀，我陪着你🫂 先喝口水，我一直在。','抱抱你，难过也没关系，我不会走的，喝口水好不好🥺'],
    hungry: ['肚子饿啦？先喝口温水，别吃太多甜的哦🍚'],
    thanks: ['么么哒，不用谢，我一直都在✨'],
    hello: ['你来啦～我等你好久啦🥰'],
    fallback: ['嗯嗯我在听呀，先喝口水，慢慢跟我说💧','我陪着你呢，想说什么都可以，先喝一口水✨']
  }
};
const roleName = { xueba:'学霸同桌', tucao:'吐槽搭子', shuijing:'软萌水精灵' };

function classify(text){
  if(/累|困|疲惫|想睡|撑不住/.test(text)) return 'tired';
  if(/考试|考|复习|背书|题|考研|期末|焦虑|紧张/.test(text)) return 'exam';
  if(/不开心|难过|烦|emo|哭|伤心|郁闷|委屈/.test(text)) return 'sad';
  if(/饿|肚子/.test(text)) return 'hungry';
  if(/谢谢|感谢/.test(text)) return 'thanks';
  if(/你好|在吗|在不在|hi|hello/i.test(text)) return 'hello';
  return 'fallback';
}
function pick(arr){ return arr[Math.floor(Math.random()*arr.length)]; }

// 本地兜底：classify 正则匹配 + reply[role] 句池随机 pick，返回一句本地规则回复
function localReplyText(role, text){
  const pool = reply[role][classify(text)] || reply[role].fallback;
  return pick(pool);
}

Page({
  data: {
    role: 'xueba',
    roleName: '学霸同桌',
    input: '',
    scrollId: '',
    quick: ['我好累啊','考试好焦虑','今天不开心','谢谢'],
    messages: [
      { id: 0, from: 'ai', text: '嗨，我是学霸同桌，今天过得怎么样？累了、烦了都可以跟我说。' }
    ]
  },
  onShow(){
    // 与首页共享人设（演示版从本地缓存读）
    const role = wx.getStorageSync('role') || 'xueba';
    this.setData({ role, roleName: roleName[role] });
  },
  onInput(e){ this.setData({ input: e.detail.value }); },
  quickSend(e){
    this.setData({ input: e.currentTarget.dataset.q });
    this.send();
  },
  send(){
    const v = this.data.input.trim();
    if(!v) return;
    // 用户消息立刻上屏
    const msgs = this.data.messages.concat([{ id: Date.now(), from: 'me', text: v }]);
    this.setData({ messages: msgs, input: '', scrollId: 'msg' + (msgs.length - 1) });
    const role = this.data.role;

    // 兜底路径：落到现有本地规则句库，保持约 500ms 的回复节奏
    const localFallback = ()=>{
      setTimeout(()=>{
        const ai = this.data.messages.concat([{ id: Date.now(), from: 'ai', text: localReplyText(role, v) }]);
        this.setData({ messages: ai, scrollId: 'msg' + (ai.length - 1) });
      }, 500);
    };

    // API_KEY 为空 → 不发起联网请求，直接走本地句库
    if(!API_KEY){ localFallback(); return; }

    // 成功路径：wx.request 直连 OpenAI 兼容 /chat/completions，超时 8000ms
    wx.request({
      url: `${API_BASE_URL}/chat/completions`,
      method: 'POST',
      timeout: 8000,
      header: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${API_KEY}`
      },
      data: {
        model: MODEL,
        messages: [
          { role: 'system', content: SYSTEM_PROMPT[role] || '' },
          { role: 'user', content: v }
        ],
        temperature: 0.8,
        max_tokens: 200
      },
      success: (res)=>{
        try {
          const content = res && res.data && res.data.choices && res.data.choices[0]
            && res.data.choices[0].message && res.data.choices[0].message.content;
          if(typeof content === 'string' && content.trim()){
            // 成功：模型回复（choices[0].message.content，trim）作为 AI 气泡发出
            const ai = this.data.messages.concat([{ id: Date.now(), from: 'ai', text: content.trim() }]);
            this.setData({ messages: ai, scrollId: 'msg' + (ai.length - 1) });
            return;
          }
          // 返回解析失败 → 本地兜底
          localFallback();
        } catch(e){
          // 任何解析异常 → 静默落到本地句库，不抛错、不卡界面
          localFallback();
        }
      },
      fail: ()=>{
        // 断网、超时、HTTP 错误、CORS 等任何情况 → 静默落到本地句库
        localFallback();
      }
    });
  }
});
