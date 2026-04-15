const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');

const installer = require('../npm/install.js');

test('downloadUrl uses release asset for linux x64', () => {
  assert.equal(
    installer.downloadUrl('0.2.8', 'linux', 'x64'),
    'https://github.com/duanluan/openai-local-bridge/releases/download/v0.2.8/olb-linux-x86_64',
  );
});

test('package json name is scoped for npm publish', () => {
  // eslint-disable-next-line global-require
  const packageJson = require('../package.json');
  assert.equal(packageJson.name, '@duanluan/openai-local-bridge');
});

test('packageSpecFor returns windows binary path', () => {
  const spec = installer.packageSpecFor('win32', 'x64');
  assert.equal(spec.releaseAsset, 'olb-windows-x86_64.exe');
  assert.equal(spec.binaryPath, 'bin/olb.exe');
});

test('packageSpecFor rejects unsupported platform', () => {
  assert.throws(() => installer.packageSpecFor('linux', 'arm64'), /unsupported platform/);
});

test('packageSpecFor localizes unsupported platform errors', () => {
  assert.throws(
    () => installer.packageSpecFor('linux', 'arm64', { OLB_LANG: 'zh_CN' }),
    /不支持的平台/,
  );
});

test('moveFile falls back to copy when rename crosses devices', async (t) => {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'olb-install-test-'));
  const source = path.join(tempDir, 'source.bin');
  const target = path.join(tempDir, 'target.bin');
  await fs.writeFile(source, 'binary');

  const originalRename = fs.rename;
  t.mock.method(fs, 'rename', async () => {
    const error = new Error('cross-device link not permitted');
    error.code = 'EXDEV';
    throw error;
  });

  await installer.moveFile(source, target);

  assert.equal(await fs.readFile(target, 'utf8'), 'binary');
  await assert.rejects(fs.access(source));

  t.mock.restoreAll();
  fs.rename = originalRename;
});
