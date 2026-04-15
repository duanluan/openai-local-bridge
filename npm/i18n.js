const messages = {
  unsupportedPlatform: {
    en: 'unsupported platform: {platform}/{arch}',
    zh: '不支持的平台：{platform}/{arch}',
  },
  missingBinary: {
    en: 'missing binary: {binaryPath}; rerun npm install openai-local-bridge',
    zh: '缺少二进制文件：{binaryPath}；请重新执行 npm install openai-local-bridge',
  },
  downloadFailed: {
    en: 'download failed: {url} ({statusCode})',
    zh: '下载失败：{url}（{statusCode}）',
  },
};

function detectLanguage(env = process.env) {
  const raw = env.OLB_LANG || env.LC_ALL || env.LC_MESSAGES || env.LANG || '';
  const normalized = raw.split('.')[0].toLowerCase().replace('-', '_');
  return normalized.startsWith('zh') ? 'zh' : 'en';
}

function format(template, values = {}) {
  return template.replace(/\{(\w+)\}/g, (_, key) => String(values[key] ?? ''));
}

function t(key, values = {}, env = process.env) {
  const catalog = messages[key];
  if (!catalog) {
    return key;
  }
  const language = detectLanguage(env);
  return format(catalog[language] || catalog.en, values);
}

module.exports = {
  detectLanguage,
  t,
};
