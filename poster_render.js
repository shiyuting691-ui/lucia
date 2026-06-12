/**
 * 海报渲染引擎 — 接收 JSON 设计稿，输出高清 PNG
 * 用法: node poster_render.js <design.json> <output.png> [width] [height]
 */
const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const THEMES = {
  urgent: {
    bg: 'linear-gradient(145deg, #0D0500 0%, #1A0800 60%, #2A0F00 100%)',
    accent: '#FF4500', accent2: '#FF8C00', accentGlow: '#FF450088',
    text: '#FFFFFF', subtext: '#FFD700', tagBg: '#FF4500',
  },
  warm: {
    bg: 'linear-gradient(145deg, #0A0515 0%, #130A2A 60%, #1E0F3D 100%)',
    accent: '#9B4DFF', accent2: '#FF6EC7', accentGlow: '#9B4DFF66',
    text: '#FFFFFF', subtext: '#D4AAFF', tagBg: '#7B2FBE',
  },
  fresh: {
    bg: 'linear-gradient(145deg, #001018 0%, #001E2C 60%, #002A3A 100%)',
    accent: '#00E5B4', accent2: '#00AAFF', accentGlow: '#00E5B466',
    text: '#FFFFFF', subtext: '#80F0D8', tagBg: '#00C9A7',
  },
  professional: {
    bg: 'linear-gradient(145deg, #080D14 0%, #0D1A2E 60%, #142040 100%)',
    accent: '#3B82F6', accent2: '#60A5FA', accentGlow: '#3B82F666',
    text: '#FFFFFF', subtext: '#94A3B8', tagBg: '#2563EB',
  },
};

function buildHTML(design, theme) {
  const t = THEMES[theme] || THEMES.warm;
  const { headline='', subheadline='', badge='', points=[], cta='立即咨询', tags=[], brand='专业留学辅导' } = design;

  const pointsHTML = points.map(p =>
    `<div class="point">${p}</div>`
  ).join('');

  const tagsHTML = tags.map(tag =>
    `<span class="tag">#${tag}</span>`
  ).join('');

  return `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;700;900&display=swap');
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    width: 1080px; height: 1440px;
    background: ${t.bg};
    font-family: 'PingFang SC', 'Noto Sans SC', 'STHeiti', sans-serif;
    color: ${t.text};
    overflow: hidden;
    position: relative;
  }

  /* 背景装饰 */
  .bg-circle-1 {
    position: absolute; top: -120px; right: -120px;
    width: 500px; height: 500px; border-radius: 50%;
    background: radial-gradient(circle, ${t.accent}30 0%, transparent 70%);
  }
  .bg-circle-2 {
    position: absolute; bottom: 80px; left: -100px;
    width: 320px; height: 320px; border-radius: 50%;
    background: radial-gradient(circle, ${t.accent2}25 0%, transparent 70%);
  }
  .bg-line {
    position: absolute; top: 0; left: 0; right: 0;
    height: 5px;
    background: linear-gradient(90deg, ${t.accent}, ${t.accent2});
  }

  /* 内容容器 */
  .container {
    position: relative; z-index: 10;
    padding: 60px 64px 48px;
    height: 100%;
    display: flex; flex-direction: column;
  }

  /* 角标 */
  .badge {
    align-self: flex-end;
    background: ${t.accent};
    color: white;
    font-size: 26px; font-weight: 700;
    padding: 8px 20px; border-radius: 8px;
    margin-bottom: 32px;
    box-shadow: 0 4px 20px ${t.accentGlow};
  }

  /* 主标题 */
  .headline {
    font-size: 88px;
    font-weight: 900;
    line-height: 1.15;
    color: ${t.accent};
    text-shadow: 0 0 40px ${t.accentGlow};
    margin-bottom: 12px;
    letter-spacing: -1px;
    word-break: break-all;
  }

  /* 分隔线 */
  .divider {
    height: 3px;
    background: linear-gradient(90deg, ${t.accent}, ${t.accent2}, transparent);
    margin: 24px 0;
    border-radius: 2px;
  }

  /* 副标题 */
  .subheadline {
    font-size: 42px; font-weight: 700;
    color: ${t.subtext};
    margin-bottom: 40px;
    line-height: 1.4;
  }

  /* 要点列表 */
  .points { flex: 1; margin-bottom: 32px; }
  .point {
    font-size: 36px; font-weight: 500;
    color: ${t.text};
    padding: 14px 20px;
    margin-bottom: 12px;
    background: rgba(255,255,255,0.05);
    border-left: 4px solid ${t.accent};
    border-radius: 0 10px 10px 0;
    line-height: 1.5;
  }

  /* 标签 */
  .tags { margin-bottom: 32px; display: flex; flex-wrap: wrap; gap: 12px; }
  .tag {
    background: ${t.tagBg}33;
    border: 1px solid ${t.accent}66;
    color: ${t.subtext};
    font-size: 26px; font-weight: 600;
    padding: 8px 18px; border-radius: 6px;
  }

  /* CTA 按钮 */
  .cta-btn {
    background: linear-gradient(135deg, ${t.accent}, ${t.accent2});
    color: white;
    font-size: 48px; font-weight: 900;
    text-align: center;
    padding: 28px;
    border-radius: 18px;
    box-shadow: 0 8px 32px ${t.accentGlow};
    letter-spacing: 4px;
    margin-bottom: 20px;
  }

  /* 品牌 */
  .brand {
    text-align: center;
    font-size: 22px; color: ${t.subtext}88;
  }
</style>
</head>
<body>
  <div class="bg-circle-1"></div>
  <div class="bg-circle-2"></div>
  <div class="bg-line"></div>
  <div class="container">
    ${badge ? `<div class="badge">${badge}</div>` : ''}
    <div class="headline">${headline}</div>
    <div class="divider"></div>
    <div class="subheadline">${subheadline}</div>
    <div class="points">${pointsHTML}</div>
    <div class="tags">${tagsHTML}</div>
    <div class="cta-btn">👉 ${cta}</div>
    <div class="brand">© ${brand}</div>
  </div>
</body>
</html>`;
}

async function render(designFile, outputFile) {
  const design = JSON.parse(fs.readFileSync(designFile, 'utf8'));
  const theme  = design.color_hint || 'warm';
  const html   = buildHTML(design, theme);

  const browser = await puppeteer.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: 'new',
    args: [
      '--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu',
      '--disable-dev-shm-usage', '--no-first-run', '--no-default-browser-check',
      '--disable-extensions', '--disable-background-networking',
    ],
  });
  const page    = await browser.newPage();
  await page.setViewport({ width: 1080, height: 1440, deviceScaleFactor: 2 });
  await page.setContent(html, { waitUntil: 'networkidle0' });
  await page.screenshot({ path: outputFile, type: 'png', fullPage: false });
  await browser.close();
  console.log('DONE:' + outputFile);
}

render(process.argv[2], process.argv[3]).catch(e => { console.error(e); process.exit(1); });
