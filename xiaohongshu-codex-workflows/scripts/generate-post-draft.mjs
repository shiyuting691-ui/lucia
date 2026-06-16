import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd());
const inputPath = path.join(root, "inputs", "post-brief.json");
const rulesPath = path.join(root, "knowledge", "sop-rules.json");
const outputPath = path.join(root, "outputs", "post-draft.md");

const brief = JSON.parse(fs.readFileSync(inputPath, "utf8"));
const rules = JSON.parse(fs.readFileSync(rulesPath, "utf8"));

const topic = brief.topic || "未命名主题";
const shortTopic = topic.replace(/如何|怎么|也能|真的|这件事/g, "").trim() || topic;
const audience = brief.targetAudience || "目标用户";
const tone = Array.isArray(brief.tone) ? brief.tone.join("、") : "真实、具体";
const evidence = Array.isArray(brief.evidence) ? brief.evidence : [];
const mustInclude = Array.isArray(brief.mustInclude) ? brief.mustInclude : [];
const role = brief.accountRole || "ip";
const funnel = brief.searchFunnel || "midstream";
const roleRule = rules.accountRoles[role] || rules.accountRoles.ip;
const funnelRule = rules.searchFunnels[funnel] || rules.searchFunnels.midstream;

const titleFactories = {
  student: [
    () => `${brief.longTailKeyword || shortTopic}`,
    () => `${shortTopic}，我真的卡住了`,
    () => `有没有人也遇到${shortTopic}`,
    () => `${shortTopic}现在该怎么办`,
    () => `这门课作业要求我看懵了`
  ],
  ip: [
    () => `${shortTopic}，先别只改词`,
    () => `AI率高时，我会先看这3个地方`,
    () => `${shortTopic}最容易误判的一步`,
    () => `改了一整天还高，问题可能不在同义词`,
    () => `KCL这类AI率问题，先分清风险来源`
  ],
  business: [
    () => `${brief.longTailKeyword || shortTopic}`,
    () => `${shortTopic}的风险不只在措辞`,
    () => `AI率78%的稿子，先按这个顺序查`,
    () => `KCL essay AI率高，常见风险点拆解`,
    () => `${shortTopic}处理前先看这几个信号`
  ]
};

const titles = (titleFactories[role] || titleFactories.ip).map((makeTitle) => makeTitle());

const bodies = {
  student: [
    `今天真的被“${topic}”卡住了。`,
    `我本来以为只是改一改就能过，但现在看起来好像不是这么简单。`,
    "",
    "现在最卡的是这几个地方：",
    "",
    `1. ${mustInclude[0] || "具体问题还没定位清楚"}。`,
    `2. ${mustInclude[1] || "试过一些办法但没有明显变化"}。`,
    `3. ${mustInclude[2] || "不知道下一步该先改哪里"}。`,
    "",
    "有没有同课或者遇到过类似情况的同学，可以说说你们是怎么处理的吗？",
    "",
    `${brief.commentQuestion || brief.cta || "我先记录一下进度，后面有结果再回来更新。"}`
  ],
  ip: [
    `最近看到不少同学卡在“${topic}”，尤其是已经改过一轮，但结果还是没有明显变化的时候，很容易越改越乱。`,
    `如果你正在面对类似情况，我会先提醒一句：${brief.coreViewpoint || "先判断风险来源，再决定怎么改。"}`,
    "",
    "我一般会先看这 3 个点：",
    "",
    `1. ${mustInclude[0] || "先看问题出现的位置"}。不要一上来全篇替换，否则很容易改散。`,
    `2. ${mustInclude[1] || "判断是不是方向错了"}。有些问题不是词的问题，而是段落推进太模板化。`,
    `3. ${mustInclude[2] || "分清局部问题和整体问题"}。局部句子能微调，整体结构不对就要重搭。`,
    "",
    "为什么我会这么判断？",
    ...evidence.map((item, index) => `${index + 1}. ${item}`),
    "",
    "所以这类问题别急着只看表面分数，先把来源拆清楚，后面改起来会稳很多。",
    "",
    `${brief.commentQuestion || brief.cta || "你现在卡在哪一步？可以说具体一点。"}`
  ],
  business: [
    `“${topic}”这类问题，真正要先看的不是单个词，而是风险来源。`,
    `对${audience}来说，比较稳的处理顺序是：先定位报告提示，再看表达重复度，最后判断是否需要重写段落结构。`,
    "",
    "建议按这个顺序排查：",
    "",
    `1. ${mustInclude[0] || "先看报告标红和提示类型"}。`,
    `2. ${mustInclude[1] || "再看是否存在同义词替换但结构没变的问题"}。`,
    `3. ${mustInclude[2] || "最后判断是否需要调整论证逻辑"}。`,
    "",
    "常见风险：",
    ...evidence.map((item, index) => `${index + 1}. ${item}`),
    "",
    "如果只改局部措辞，短期看起来有变化，但整体风险可能还在。",
    "",
    `${brief.commentQuestion || brief.cta || "可以说一下你现在卡在报告解释、结构重写还是引用处理。"}`
  ]
};

const body = (bodies[role] || bodies.ip).join("\n");

const markdown = [
  "# 发帖草稿",
  "",
  "## 定位",
  "",
  `- 账号角色：${roleRule.name}`,
  `- 角色任务：${roleRule.job}`,
  `- 搜索阶段：${funnelRule.name}`,
  `- 用户意图：${funnelRule.intent}`,
  `- 长尾词：${brief.longTailKeyword || "未填写"}`,
  "",
  "## 标题候选",
  "",
  ...titles.map((title, index) => `${index + 1}. ${title}`),
  "",
  "## 正文草稿",
  "",
  body,
  "",
  "## 口吻提醒",
  "",
  `- 建议保持：${tone}`,
  `- 推荐结构：${rules.contentModel.recommended}`,
  "- 发布前再人工补入真实细节、案例边界和配图说明。",
  "",
  "## 合规检查",
  "",
  "- 正文不写硬引流。",
  "- 不做绝对承诺。",
  "- 评论问题要围绕具体卡点。",
  "- 不使用批量复制式评论话术。"
].join("\n");

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, markdown);

console.log(`已生成 ${outputPath}`);
