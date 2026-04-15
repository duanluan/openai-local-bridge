#!/usr/bin/env node

const fs = require('node:fs');
const fsp = require('node:fs/promises');
const https = require('node:https');
const os = require('node:os');
const path = require('node:path');

const { t } = require('./i18n.js');
const packageRoot = path.resolve(__dirname, '..');
const packageJson = require('../package.json');
const platformPackages = require('./platforms.json');

function platformKey(platform = process.platform, arch = process.arch) {
  return `${platform}-${arch}`;
}

function packageSpecFor(platform = process.platform, arch = process.arch, env = process.env) {
  const spec = platformPackages[platformKey(platform, arch)];
  if (!spec) {
    throw new Error(t('unsupportedPlatform', { platform, arch }, env));
  }
  return spec;
}

function downloadUrl(version = packageJson.version, platform = process.platform, arch = process.arch, env = process.env) {
  const spec = packageSpecFor(platform, arch, env);
  return `https://github.com/duanluan/openai-local-bridge/releases/download/v${version}/${spec.releaseAsset}`;
}

function downloadFile(url, destination) {
  return new Promise((resolve, reject) => {
    const request = https.get(
      url,
      {
        headers: {
          'User-Agent': 'openai-local-bridge-npm-installer',
        },
      },
      (response) => {
        if (response.statusCode && response.statusCode >= 300 && response.statusCode < 400 && response.headers.location) {
          response.resume();
          downloadFile(response.headers.location, destination).then(resolve, reject);
          return;
        }

        if (response.statusCode !== 200) {
          response.resume();
          reject(new Error(t('downloadFailed', { url, statusCode: response.statusCode })));
          return;
        }

        const file = fs.createWriteStream(destination, { mode: 0o755 });
        response.pipe(file);
        file.on('finish', () => file.close(resolve));
        file.on('error', reject);
      },
    );
    request.on('error', reject);
  });
}

async function moveFile(sourcePath, targetPath) {
  try {
    await fsp.rename(sourcePath, targetPath);
  } catch (error) {
    if (error && error.code === 'EXDEV') {
      await fsp.copyFile(sourcePath, targetPath);
      await fsp.unlink(sourcePath);
      return;
    }
    throw error;
  }
}

async function installBinary() {
  const spec = packageSpecFor();
  const binaryPath = path.join(__dirname, spec.binaryPath);
  const tempPath = path.join(os.tmpdir(), `${spec.releaseAsset}-${process.pid}`);

  await fsp.mkdir(path.dirname(binaryPath), { recursive: true });
  await downloadFile(downloadUrl(), tempPath);
  await moveFile(tempPath, binaryPath);

  if (process.platform !== 'win32') {
    await fsp.chmod(binaryPath, 0o755);
  }
}

async function main() {
  if (process.env.OLB_SKIP_BINARY_DOWNLOAD === '1') {
    return;
  }
  await installBinary();
}

module.exports = {
  downloadUrl,
  installBinary,
  main,
  moveFile,
  packageSpecFor,
  platformKey,
};

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message || String(error));
    process.exit(1);
  });
}
