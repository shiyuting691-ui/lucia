import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd());
const courseBankPath = path.join(root, "outputs", "course-context-bank.json");
const outputJsonPath = path.join(root, "outputs", "course-precision-post-drafts.json");
const outputMdPath = path.join(root, "outputs", "course-precision-post-drafts.md");

const roleNames = {
  student: "学生号",
  ip: "IP号",
  business: "业务号"
};

const readJson = (filePath, fallback) => {
  if (!fs.existsSync(filePath)) return fallback;
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
};

const compact = (value = "", limit = 80) => {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
};

const labelCourse = (course) =>
  [course.university, course.courseCode, course.courseTitle].filter(Boolean).join(" ") || "未命名课程";

const labelAssessment = (course) => {
  const assessment = course.assessment || {};
  return [
    assessment.weight,
    assessment.type || assessment.deliverable,
    assessment.deadline ? `DDL ${assessment.deadline}` : ""
  ].filter(Boolean).join(" / ") || "assessment信息待补";
};

const angleFor = (course) => {
  const assessment = course.assessment || {};
  if (/ddl|deadline|due|今晚|明天|急/i.test(`${assessment.deadline} ${course.studentNeed}`)) return "ddl-rescue";
  if (assessment.rubricFocus?.length || /rubric|评分|criteria/i.test(`${course.studentNeed} ${assessment.deliverable}`)) return "rubric";
  if (/ai|turnitin|重复率|ai率/i.test(`${course.studentNeed} ${assessment.deliverable}`)) return "ai-risk";
  if (/exam|final|考试/i.test(`${assessment.type} ${assessment.deliverable}`)) return "exam";
  return "brief-breakdown";
};

const buildStudent = (course) => {
  const courseLabel = labelCourse(course);
  const assessmentLabel = labelAssessment(course);
  const rubric = course.assessment?.rubricFocus?.[0] || "rubric里的关键词";
  return {
    role: "student",
    roleName: roleNames.student,
    titleOptions: [
      `${course.courseCode || course.courseTitle || "这个课"}的作业我真的看不懂`,
      `${assessmentLabel}，我现在有点慌`,
      `有没有同课的人知道第一步怎么开始`
    ],
    body: [
      `我现在卡在 ${courseLabel} 这个 assessment 上。`,
      "",
      `brief打开了，${assessmentLabel}也看到了，但越看越不知道第一步该干嘛。`,
      "",
      "最崩的是这几个点：",
      `1. ${rubric} 到底要写到什么程度，我完全没底。`,
      `2. ${course.studentNeed || "不知道先找资料、列outline，还是先看例子"}。`,
      "3. 一想到后面还要补引用、改结构、压DDL，就开始逃避。",
      "",
      "有没有同课/同类型作业的人，你们第一步是怎么拆的？"
    ].join("\n"),
    coverText: `${course.courseCode || "assessment"}\n我真看不懂`,
    commentPrompt: "你们是先看rubric，还是先搭outline？"
  };
};

const buildIp = (course) => {
  const courseLabel = labelCourse(course);
  const assessmentLabel = labelAssessment(course);
  const rubricFocus = course.assessment?.rubricFocus?.slice(0, 3).join(" / ") || "analysis / evidence / structure";
  return {
    role: "ip",
    roleName: roleNames.ip,
    titleOptions: [
      `${course.courseCode || course.courseTitle || "assessment"}先别急着写，先拆评分点`,
      `看不懂brief时，先按这3步拆`,
      `${course.assessment?.type || "作业"}最容易误判的不是字数`
    ],
    body: [
      `${courseLabel} 这类 ${course.assessment?.type || "assessment"}，不要一上来就直接写正文。`,
      "",
      `先把 ${assessmentLabel} 拆清楚，再决定先救哪一块。`,
      "",
      "我会先看 3 件事：",
      `1. 交付物是什么：${course.assessment?.deliverable || "先确认到底交essay、report、presentation还是exam"}`,
      `2. rubric关键词是什么：${rubricFocus}`,
      `3. 学生当前卡点是什么：${course.studentNeed || "是不会开始，还是已经写了但结构很散"}`,
      "",
      "很多人不是不会写，而是第一步拆错了，后面就会越写越慌。",
      "",
      "你现在卡在brief理解、资料、outline，还是正文推进？"
    ].join("\n"),
    coverText: `${course.courseCode || "brief"}\n先拆评分点`,
    commentPrompt: "你现在更像方向不清，还是时间不够？"
  };
};

const buildBusiness = (course) => {
  const courseLabel = labelCourse(course);
  const assessmentLabel = labelAssessment(course);
  return {
    role: "business",
    roleName: roleNames.business,
    titleOptions: [
      `${course.courseCode || course.courseTitle || "作业"}卡住时，先做风险排查`,
      `${course.assessment?.type || "assessment"}求助前，先确认这3点`,
      `DDL前别乱改，先判断问题在哪`
    ],
    body: [
      `${courseLabel} 这种需求，不能只看“会不会写”，要先判断 assessment 风险在哪里。`,
      "",
      `当前最关键的信息是：${assessmentLabel}。这决定了内容应该做计划、拆题，还是风险排查。`,
      "",
      "建议先按这个顺序看：",
      `1. 任务类型：${course.assessment?.type || "先确认assessment类型"}。`,
      `2. 评分重点：${course.assessment?.rubricFocus?.slice(0, 3).join(" / ") || "rubric、证据、结构、引用"}`,
      `3. 当前卡点：${course.studentNeed || "是完全不会开始，还是已经写了但不确定方向"}`,
      "",
      "只有先判断清楚风险，后面才知道该补资料、重搭结构，还是局部修改。",
      "",
      "你现在卡的是题目理解、资料整理、正文推进，还是DDL安排？"
    ].join("\n"),
    coverText: `${course.courseCode || "作业"}\n风险排查顺序`,
    commentPrompt: "你现在最紧急的是DDL、结构、引用，还是AI率？"
  };
};

const buildDrafts = (course, index) => {
  const angle = angleFor(course);
  const builders = [buildStudent, buildIp, buildBusiness];
  return builders.map((builder) => {
    const draft = builder(course);
    return {
      id: `course-${index + 1}-${draft.role}`,
      status: "ready",
      course: {
        label: labelCourse(course),
        university: course.university || "",
        courseCode: course.courseCode || "",
        courseTitle: course.courseTitle || "",
        academicYear: course.academicYear || ""
      },
      assessment: course.assessment || {},
      studentNeed: course.studentNeed || "",
      angle,
      precisionSources: course.officialSources || [],
      checks: [
        "不要写死未验证的官方事实",
        "课程截图/作业要求需打码",
        "学生号不能出现服务口吻",
        "业务号不承诺结果、不写保分"
      ],
      ...draft
    };
  });
};

const courseBank = readJson(courseBankPath, []);
const courses = Array.isArray(courseBank) ? courseBank.filter((item) => item.enabled) : [];
const drafts = courses.flatMap((course, index) => buildDrafts(course, index));

const markdown = [
  "# 课程作业精细化发帖草稿",
  "",
  `生成时间：${new Date().toLocaleString("zh-CN", { hour12: false })}`,
  `课程数量：${courses.length}`,
  `草稿数量：${drafts.length}`,
  "",
  "> 来源优先级：飞书课程作业信息。没有官网/官方文件链接时，发布前不要写死具体政策或DDL。",
  "",
  ...courses.flatMap((course, courseIndex) => {
    const courseDrafts = drafts.filter((draft) => draft.id.startsWith(`course-${courseIndex + 1}-`));
    return [
      `## ${courseIndex + 1}. ${labelCourse(course)}`,
      "",
      `- 评估：${labelAssessment(course)}`,
      `- 学生需求：${course.studentNeed || "未填写"}`,
      `- 评分点：${course.assessment?.rubricFocus?.join(" / ") || "未填写"}`,
      `- 来源：${course.officialSources?.length ? course.officialSources.map((item) => item.url || item.title).join("；") : "飞书表格，待补官方链接"}`,
      "",
      ...courseDrafts.flatMap((draft) => [
        `### ${draft.roleName}`,
        "",
        "标题备选：",
        ...draft.titleOptions.map((title, index) => `${index + 1}. ${title}`),
        "",
        `封面：${draft.coverText.replace(/\n/g, " / ")}`,
        "",
        "正文：",
        "",
        draft.body,
        "",
        `评论引导：${draft.commentPrompt}`,
        "",
        "发布前检查：",
        ...draft.checks.map((check) => `- [ ] ${check}`),
        ""
      ])
    ];
  }),
  courses.length ? "" : "暂无课程作业信息。请先配置飞书表格并运行 `npm run collect:lark`。"
].join("\n");

fs.mkdirSync(path.dirname(outputJsonPath), { recursive: true });
fs.writeFileSync(outputJsonPath, JSON.stringify({
  generatedAt: new Date().toISOString(),
  courseCount: courses.length,
  draftCount: drafts.length,
  drafts
}, null, 2));
fs.writeFileSync(outputMdPath, markdown);

console.log(`已生成 ${outputJsonPath}`);
console.log(`已生成 ${outputMdPath}`);
console.log(`课程精细化草稿 ${drafts.length} 条。`);
