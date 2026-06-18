import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd());
const roleHotpostsPath = path.join(root, "outputs", "social-assistant-role-hotposts.json");
const rulesPath = path.join(root, "knowledge", "sop-rules.json");
const courseContextPath = path.join(root, "inputs", "course-context.json");
const outputMdPath = path.join(root, "outputs", "role-based-post-drafts.md");
const outputJsonPath = path.join(root, "outputs", "role-based-post-drafts.json");
const visualMdPath = path.join(root, "outputs", "visual-package.md");
const visualJsonPath = path.join(root, "outputs", "visual-package.json");

const rules = JSON.parse(fs.readFileSync(rulesPath, "utf8"));
const courseContext = fs.existsSync(courseContextPath)
  ? JSON.parse(fs.readFileSync(courseContextPath, "utf8"))
  : { enabled: false };
const roleHotposts = fs.existsSync(roleHotpostsPath)
  ? JSON.parse(fs.readFileSync(roleHotpostsPath, "utf8"))
  : { student: [], ip: [], business: [] };
const runId = process.env.XHS_RUN_ID || "";
const rotationSeed = process.env.XHS_ROTATION_DATE || runId.slice(0, 10) || new Date().toISOString().slice(0, 10);
const rotationDayIndex = Math.floor(new Date(`${rotationSeed}T00:00:00Z`).getTime() / 86400000);

const roleNames = {
  student: "学生号",
  ip: "IP号",
  business: "业务号"
};

const funnelNames = {
  upstream: "上游词",
  midstream: "中游词",
  downstream: "下游词"
};

const compact = (text = "", limit = 120) => {
  const value = String(text).replace(/\s+/g, " ").trim();
  return value.length > limit ? `${value.slice(0, limit)}...` : value;
};

const extractKeyword = (post) => {
  if (post.longTailKeyword && post.longTailKeyword !== "小红书热帖") return post.longTailKeyword;
  const keyword = post.notes?.match(/关键词：([^；]+)/)?.[1];
  return keyword || post.topic || post.title;
};

const hashText = (value) => {
  let hash = 0;
  for (const char of String(value)) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  }
  return hash;
};

const rotateItems = (items, offset) => {
  if (!items.length) return [];
  const start = offset % items.length;
  return [...items.slice(start), ...items.slice(0, start)];
};

const hasCourseContext = Boolean(
  courseContext.enabled &&
  (courseContext.courseCode || courseContext.courseTitle || courseContext.assessment?.type || courseContext.assessment?.deadline)
);

const courseLabel = () => {
  if (!hasCourseContext) return "";
  return [courseContext.university, courseContext.courseCode, courseContext.courseTitle]
    .filter(Boolean)
    .join(" ");
};

const assessmentLabel = () => {
  if (!hasCourseContext) return "";
  const assessment = courseContext.assessment || {};
  return [
    assessment.weight ? `${assessment.weight}` : "",
    assessment.type || assessment.deliverable || "",
    assessment.deadline ? `DDL ${assessment.deadline}` : ""
  ].filter(Boolean).join(" / ");
};

const precisionNote = (role) => {
  if (!hasCourseContext) {
    return {
      status: "missing",
      text: "未接入官方课程信息：当前精细化只能基于社媒助手爆帖和账号SOP，不能写具体课程DDL/评分标准。"
    };
  }

  const sourceCount = Array.isArray(courseContext.officialSources)
    ? courseContext.officialSources.length
    : 0;

  return {
    status: sourceCount ? "official" : "needs_source",
    text: [
      `课程：${courseLabel()}`,
      `评估：${assessmentLabel() || "未填写"}`,
      `学生下一步：${courseContext.studentNeed || courseContext.studentStage || "未填写"}`,
      `账号切入：${roleNames[role]}`
    ].join("；")
  };
};

const pickPosts = (role) => {
  const posts = Array.isArray(roleHotposts[role]) ? roleHotposts[role] : [];
  const seen = new Set();
  const uniquePosts = posts.filter((post) => {
    const key = post.url || post.title;
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  const offset = rotationDayIndex + hashText(role);
  return rotateItems(uniquePosts, offset).slice(0, 3);
};

const titleCandidates = {
  student: (post, keyword) => [
    hasCourseContext ? `${courseContext.courseCode || keyword}这个${courseContext.assessment?.type || "assessment"}我真看不懂` : `${keyword}真的把我整不会了`,
    hasCourseContext ? `${assessmentLabel()}，我现在有点慌` : `有没有人也在被${keyword}折磨`,
    `${post.title}，我懂这种崩溃`
  ],
  ip: (post, keyword) => [
    hasCourseContext ? `${courseContext.courseCode || keyword}先别急着写，先拆assessment` : `${keyword}，先别急着硬背`,
    hasCourseContext ? `${courseContext.assessment?.type || "assignment"}最容易误判的是评分点` : `final季最容易误判的不是不会，是复习顺序`,
    `从这类爆帖看，留学生最想要的不是鸡血`
  ],
  business: (post, keyword) => [
    hasCourseContext ? `${courseContext.courseCode || keyword}卡住时，先按这3步排查` : `${keyword}卡住时，先按这3步排查`,
    `final/essay求助前，先看清楚问题在哪`,
    `${post.title}背后的真实需求拆解`
  ]
};

const hashtags = {
  student: ["英国留学", "英国final", "留学生日常", "留学生考试", "final季"],
  ip: ["英国留学", "final复习", "留学生经验", "essay", "学习方法"],
  business: ["英国留学", "留学生作业", "essay辅导", "dissertation", "final"]
};

const checks = {
  student: [
    "不出现服务、机构、咨询口吻",
    "补充真实学生细节，避免像营销号",
    "结尾用求助或共鸣，不做硬引流"
  ],
  ip: [
    "像学姐/老师复盘，不要像广告",
    "给判断框架，不承诺结果",
    "评论问题围绕具体卡点"
  ],
  business: [
    "专业但不生硬，不写绝对承诺",
    "正文不强引流",
    "用案例边界和流程说明建立信任"
  ]
};

const detectVisualSignals = (draft) => {
  const text = [
    draft.titleCandidates?.join(" "),
    draft.sourceTitle,
    draft.keyword,
    draft.body,
    draft.inspirations?.map((item) => item.title).join(" ")
  ].filter(Boolean).join(" ").toLowerCase();

  const tests = [
    ["ai-rate", /ai率|ai rate|turnitin|aigc|机器|改词|同义词|降/i],
    ["rubric-reference", /rubric|reference|referencing|citation|analysis|evaluation|evidence|评分|引用|参考文献/i],
    ["ddl", /ddl|deadline|due|还有\d|只剩|明天|今晚|快到了|倒推/i],
    ["exam-final", /final|exam|考试|复习|past paper|lecture|考场|背/i],
    ["essay-dissertation", /essay|report|proposal|dissertation|论文|作业|assessment/i]
  ];

  const matched = tests.filter(([, pattern]) => pattern.test(text)).map(([name]) => name);
  const primary = matched[0] || "general-study";
  return {
    primary,
    matched,
    needsRubricImage: matched.includes("rubric-reference") || matched.includes("essay-dissertation"),
    needsChatImage: draft.role === "student" || matched.includes("exam-final"),
    needsTimeline: matched.includes("ddl") || matched.includes("exam-final"),
    needsRiskFlow: draft.role === "business" || matched.includes("ai-rate")
  };
};

const studentSlidesBySignal = (signals) => {
  if (signals.primary === "ai-rate") {
    return [
      { kind: "student-desk", text: "电脑屏幕：AI report 打开但关键内容打码，旁边便签写“不是只改词”" },
      { kind: "student-chat", text: "微信聊天：改了半天还是高，朋友问是不是结构太像模板" },
      { kind: "student-rubric", text: "打码报告截图：圈出 repeated phrasing / source use / structure" },
      { kind: "student-comment", text: "评论引导：你是报告看不懂，还是改完还是不降？" }
    ];
  }

  if (signals.primary === "rubric-reference") {
    return [
      { kind: "student-desk", text: "学习桌面：reference / rubric / lecture notes 摊开，突出不知道先看哪一块" },
      { kind: "student-chat", text: "微信聊天：reference真的要背吗，analysis和evaluation到底差在哪" },
      { kind: "student-rubric", text: "打码assessment截图：圈出 analysis / evidence / reference" },
      { kind: "student-comment", text: "评论引导：有没有同课的人知道rubric怎么拆？" }
    ];
  }

  if (signals.primary === "ddl") {
    return [
      { kind: "student-desk", text: "学习桌面：日历和倒计时便签，突出DDL越来越近" },
      { kind: "student-countdown", text: "倒计时页：还剩几天，先救能交的部分" },
      { kind: "student-chat", text: "微信聊天：有人开始算最低要考几分/最低要写多少了" },
      { kind: "student-comment", text: "评论引导：你们ddl前最后几天先救哪一块？" }
    ];
  }

  return [
    { kind: "student-desk", text: "学习桌面：lecture没看完、past paper、rubric??" },
    { kind: "student-chat", text: "微信聊天：final复习进度互相崩溃" },
    { kind: "student-rubric", text: "打码assessment截图：只保留关键词，避免泄露课程信息" },
    { kind: "student-comment", text: "评论引导：有没有同样final硬撑的同学？" }
  ];
};

const ipSlidesBySignal = (signals) => {
  if (signals.primary === "rubric-reference") {
    return [
      { kind: "ip-framework", text: "首图：rubric不是装饰，先看得分动词" },
      { kind: "ip-rubric", text: "评分点拆解：analysis / evidence / reference 分别要做什么" },
      { kind: "ip-timeline", text: "倒推计划：先搭结构，再补证据，再修引用" },
      { kind: "ip-mistakes", text: "常见误区：只找资料，不回应评分标准" },
      { kind: "ip-comment", text: "评论问题：你现在卡在题目、证据还是引用？" }
    ];
  }

  if (signals.primary === "ai-rate") {
    return [
      { kind: "ip-framework", text: "首图：AI率高时，先别只改词" },
      { kind: "ip-rubric", text: "风险来源：句式重复 / 结构模板 / paraphrase太浅" },
      { kind: "ip-timeline", text: "处理顺序：看报告位置 -> 判断结构 -> 局部重写" },
      { kind: "ip-mistakes", text: "常见误区：全篇同义词替换，越改越奇怪" },
      { kind: "ip-comment", text: "评论问题：你是报告看不懂还是改完不降？" }
    ];
  }

  return [
    { kind: "ip-framework", text: "首图：final前先看任务类型，不要直接硬背" },
    { kind: "ip-rubric", text: "拆解：考试 / essay / report / dissertation 的重点不同" },
    { kind: "ip-timeline", text: "倒推计划：先救高权重，再救能提分的部分" },
    { kind: "ip-mistakes", text: "常见误区：只看lecture，不看评分方式" },
    { kind: "ip-comment", text: "评论问题：你现在是时间不够还是方向不清？" }
  ];
};

const businessSlidesBySignal = (signals) => {
  if (signals.primary === "ai-rate") {
    return [
      { kind: "business-flow", text: "首图：AI率风险排查顺序" },
      { kind: "business-risk", text: "高风险信号：整段模板化、引用解释浅、句式重复" },
      { kind: "business-table", text: "判断表：能局部改 / 需要重搭结构 / 不建议硬改" },
      { kind: "business-boundary", text: "边界说明：不承诺结果，先看报告和原文" },
      { kind: "business-comment", text: "评论问题：你卡在报告解释还是结构重写？" }
    ];
  }

  if (signals.primary === "rubric-reference") {
    return [
      { kind: "business-flow", text: "首图：rubric/assessment 卡住先按这3步排查" },
      { kind: "business-risk", text: "高风险信号：题目理解偏、证据不足、引用不规范" },
      { kind: "business-table", text: "判断表：brief / rubric / source / structure" },
      { kind: "business-boundary", text: "边界说明：官方信息看不到的DDL不能乱写" },
      { kind: "business-comment", text: "评论问题：你卡在题目、资料还是正文推进？" }
    ];
  }

  return [
    { kind: "business-flow", text: "首图：final卡住的排查顺序" },
    { kind: "business-risk", text: "任务类型判断：exam / essay / report / dissertation" },
    { kind: "business-table", text: "高风险信号：DDL、AI率、rubric、证据不足" },
    { kind: "business-boundary", text: "能处理/不能处理边界" },
    { kind: "business-comment", text: "评论区诊断问题" }
  ];
};

const visualPlans = {
  student: (draft) => {
    const signals = detectVisualSignals(draft);
    return {
      signals,
      style: `真实学生截图感；按内容自动匹配：${signals.primary}`,
      coverText: hasCourseContext
        ? `${courseContext.courseCode || draft.keyword}\n我真的看不懂`
        : `${draft.keyword}\n救命我真不会`,
      slides: studentSlidesBySignal(signals)
    };
  },
  ip: (draft) => {
    const signals = detectVisualSignals(draft);
    return {
      signals,
      style: `学姐拆解感；按内容自动匹配：${signals.primary}`,
      coverText: hasCourseContext
        ? `${courseContext.courseCode || draft.keyword}\n先拆评分点`
        : `${draft.keyword}\n先看这3点`,
      slides: ipSlidesBySignal(signals)
    };
  },
  business: (draft) => {
    const signals = detectVisualSignals(draft);
    return {
      signals,
      style: `专业流程图；按内容自动匹配：${signals.primary}`,
      coverText: hasCourseContext
        ? `${courseContext.courseCode || draft.keyword}\n风险排查顺序`
        : `${draft.keyword}\n排查顺序`,
      slides: businessSlidesBySignal(signals)
    };
  }
};

const bodyFactories = {
  student: (post, inspirations, keyword) => [
    hasCourseContext
      ? `我现在真的卡在${courseLabel()}这个${courseContext.assessment?.type || "assessment"}上了。`
      : `今天刷到“${post.title}”，真的很像我最近在${keyword}里那种卡住的状态。`,
    "",
    hasCourseContext
      ? `明明brief也打开了，${assessmentLabel() || "ddl/要求"}也看到了，但就是越看越不知道第一步该干嘛。`
      : "不是那种完全没学，而是明明也在努力，但越看越觉得自己哪里都没准备好。",
    "",
    "我现在最崩的是这几个点，真的不是装的：",
    "",
    hasCourseContext
      ? `1. ${courseContext.assessment?.rubricFocus?.[0] || "rubric里的关键词"}我不知道到底要写到什么程度。`
      : "1. 复习/写作的范围太散，不知道先抓哪一块。",
    hasCourseContext
      ? `2. ${courseContext.studentNeed || "下一步"}到底是先找资料、列outline，还是先看例子。`
      : "2. 看别人好像都很稳，自己就更焦虑。",
    hasCourseContext
      ? "3. 一想到后面可能还要改格式/引用/结构，就直接想把电脑合上。"
      : "3. 明知道要开始，但一坐下来就想逃避。",
    "",
    `刚好又刷到“${inspirations[1]?.title || post.title}”这种帖子，感觉大家表面都在开玩笑，其实背后都快碎了。`,
    "",
    hasCourseContext
      ? `有没有同课/同类型assessment的人，你们第一步是怎么开始的？`
      : "有没有也在final/essay阶段硬撑的同学？你们现在最卡的是复习、写作，还是ddl？"
  ],
  ip: (post, inspirations, keyword) => [
    hasCourseContext
      ? `如果是${courseLabel()}这种${courseContext.assessment?.type || "assessment"}，我不会建议一上来就直接写正文。`
      : `最近看${keyword}相关爆帖，我发现一个很明显的共同点：真正能引发收藏和评论的，不是“我有多努力”，而是把一个具体卡点说清楚。`,
    "",
    hasCourseContext
      ? `先把${assessmentLabel() || "assessment要求"}拆清楚，再决定先救哪一块，不然很容易越做越散。`
      : `比如“${post.title}”这种标题，第一眼就让人知道：这是一个真实场景，不是空泛鸡汤。`,
    "",
    "我会先拆成 3 层：",
    "",
    hasCourseContext
      ? `1. 先看占比和交付物：${assessmentLabel() || "这部分决定你要投入多少时间"}。`
      : "1. 先说具体场景。是final前3天、essay卡引用，还是dissertation不知道怎么推进。",
    hasCourseContext
      ? `2. 再看rubric关键词：${courseContext.assessment?.rubricFocus?.slice(0, 3).join(" / ") || "analysis / evidence / structure"}，这些才是得分点。`
      : "2. 再说误区。比如只背重点、只改词、只找资料，但没有解决真正的问题。",
    hasCourseContext
      ? "3. 最后倒推DDL：先完成能交的结构，再补证据和表达。"
      : "3. 最后给一个小判断。让读者知道自己下一步该先看哪里。",
    "",
    `这也是为什么“${inspirations[1]?.title || post.title}”这类内容容易被互动：它不是标准答案，而是替读者说出了一个具体困境。`,
    "",
    "你现在更像是时间不够、方向不清，还是已经开始做但做不下去？"
  ],
  business: (post, inspirations, keyword) => [
    hasCourseContext
      ? `${courseLabel()}这类需求，不能只看“会不会写”，要先判断assessment风险在哪里。`
      : `从${keyword}这批爆帖看，很多留学生不是单纯“不会”，而是卡在判断顺序上。`,
    "",
    hasCourseContext
      ? `当前信息里最关键的是：${assessmentLabel() || "评估方式/DDL/评分点"}。这决定了内容该写成计划、拆题，还是风险排查。`
      : `像“${post.title}”这类内容之所以容易爆，是因为它背后有明确需求：时间紧、任务重、风险不确定。`,
    "",
    "遇到这类问题，建议先按这个顺序排查：",
    "",
    "1. 先确认任务类型。是考试复习、essay、report，还是dissertation阶段问题。",
    "2. 再确认最紧急风险。是ddl、分数、AI率、引用，还是完全不知道怎么下手。",
    "3. 最后决定处理方式。能局部调整就不要全篇推翻，结构错了才需要重搭。",
    "",
    `如果只是看“${inspirations[1]?.title || post.title}”的表面情绪，很容易错过真正的需求点。`,
    "",
    "你现在卡的是时间安排、题目理解、资料整理，还是正文推进？"
  ]
};

const buildDraft = (role) => {
  const inspirations = pickPosts(role);
  const source = inspirations[0];
  const roleRule = rules.accountRoles[role];

  if (!source) {
    return {
      role,
      roleName: roleNames[role],
      status: "empty",
      message: "暂无足够的社媒助手爆帖样本。"
    };
  }

  const keyword = extractKeyword(source);
  const titles = titleCandidates[role](source, keyword);
  const body = bodyFactories[role](source, inspirations, keyword).join("\n");
  const precision = precisionNote(role);

  const draft = {
    role,
    roleName: roleNames[role],
    status: "ready",
    sourceTitle: source.title,
    sourceUrl: source.url,
    sourceMetrics: {
      likes: source.likes,
      comments: source.comments,
      favorites: source.favorites
    },
    searchFunnel: source.searchFunnel,
    searchFunnelName: funnelNames[source.searchFunnel] || source.searchFunnel,
    keyword,
    precision,
    roleJob: roleRule?.job || "",
    voice: roleRule?.voice || "",
    titleCandidates: titles,
    coverIdea: role === "student"
      ? `大字情绪封面：${keyword} 救命`
      : role === "ip"
        ? `备忘录拆解封面：${keyword} 先看这3点`
        : `流程图封面：${keyword} 排查顺序`,
    hashtags: hashtags[role],
    body,
    checks: checks[role],
    inspirations: inspirations.map((post) => ({
      title: post.title,
      url: post.url,
      metrics: `赞${post.likes} / 评${post.comments} / 藏${post.favorites}`,
      reason: compact(post.notes, 140)
    }))
  };

  draft.visualPlan = visualPlans[role](draft);
  return draft;
};

const drafts = ["student", "ip", "business"].map(buildDraft);

const markdown = [
  "# 三账号 SOP 发帖草稿",
  "",
  `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
  "",
  "> 来源：社媒助手爆帖池。学生号/IP号/业务号分别按不同 SOP 选爆帖和出稿，发布前仍需人工确认真实细节、封面和合规边界。",
  "",
  ...drafts.flatMap((draft) => {
    if (draft.status !== "ready") {
      return [`## ${draft.roleName}`, "", draft.message, ""];
    }

    return [
      `## ${draft.roleName}`,
      "",
      "### 爆帖来源",
      "",
      `- 主样本：${draft.sourceTitle}`,
      `- 数据：赞${draft.sourceMetrics.likes} / 评${draft.sourceMetrics.comments} / 藏${draft.sourceMetrics.favorites}`,
      `- 阶段：${draft.searchFunnelName}`,
      `- 长尾词：${draft.keyword}`,
      `- 角色任务：${draft.roleJob}`,
      `- 口吻：${draft.voice}`,
      `- 精细化状态：${draft.precision.text}`,
      "",
      "### 参考爆帖",
      "",
      ...draft.inspirations.map((item, index) => `${index + 1}. ${item.title}（${item.metrics}）`),
      "",
      "### 标题候选",
      "",
      ...draft.titleCandidates.map((title, index) => `${index + 1}. ${title}`),
      "",
      "### 封面思路",
      "",
      draft.coverIdea,
      "",
      "### 图片发布包",
      "",
      `- 风格：${draft.visualPlan.style}`,
      `- 内容信号：${draft.visualPlan.signals.matched.join("、") || draft.visualPlan.signals.primary}`,
      `- 首图文字：${draft.visualPlan.coverText.replace(/\n/g, " / ")}`,
      ...draft.visualPlan.slides.map((slide) => `- ${slide.text || slide}`),
      "",
      "### 正文草稿",
      "",
      draft.body,
      "",
      "### 标签",
      "",
      draft.hashtags.map((tag) => `#${tag}`).join(" "),
      "",
      "### 发布前检查",
      "",
      ...draft.checks.map((check) => `- [ ] ${check}`),
      "- [ ] 人工补入真实细节、截图或案例边界",
      "- [ ] 人工确认可以对外发布",
      ""
    ];
  })
].join("\n");

fs.mkdirSync(path.dirname(outputMdPath), { recursive: true });
fs.writeFileSync(outputMdPath, markdown);
fs.writeFileSync(outputJsonPath, JSON.stringify({ generatedAt: new Date().toISOString(), drafts }, null, 2));

const visualMarkdown = [
  "# 小红书图片发布包",
  "",
  `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
  "",
  "> 这个文件用于人工制作或交给设计工具生成图片。发布前请替换为真实截图、课程信息或打码后的素材。",
  "",
  ...drafts.flatMap((draft) => {
    if (draft.status !== "ready") return [];
    return [
      `## ${draft.roleName}`,
      "",
      `- 标题：${draft.titleCandidates[0]}`,
      `- 风格：${draft.visualPlan.style}`,
      `- 内容信号：${draft.visualPlan.signals.matched.join("、") || draft.visualPlan.signals.primary}`,
      `- 首图文字：${draft.visualPlan.coverText.replace(/\n/g, " / ")}`,
      "",
      "### 图片结构",
      "",
      ...draft.visualPlan.slides.map((slide, index) => `${index + 1}. ${slide.text || slide}`),
      "",
      "### 素材要求",
      "",
      "- 课程/DDL/评分截图必须打码。",
      "- 不放联系方式或硬引流。",
      "- 学生号图片要像真实记录，业务号图片要像流程说明。",
      ""
    ];
  })
].join("\n");

fs.writeFileSync(visualMdPath, visualMarkdown);
fs.writeFileSync(visualJsonPath, JSON.stringify({
  generatedAt: new Date().toISOString(),
  visuals: drafts
    .filter((draft) => draft.status === "ready")
    .map((draft) => ({
      role: draft.role,
      roleName: draft.roleName,
      title: draft.titleCandidates[0],
      ...draft.visualPlan
    }))
}, null, 2));

console.log(`已生成 ${outputMdPath}`);
console.log(`已生成 ${outputJsonPath}`);
console.log(`已生成 ${visualMdPath}`);
console.log(`已生成 ${visualJsonPath}`);
