const test = require('node:test');
const assert = require('node:assert/strict');

const launcher = require('../npm/olb.js');

test('platformKey builds npm platform key', () => {
  assert.equal(launcher.platformKey('linux', 'x64'), 'linux-x64');
});

test('packageSpecFor returns configured platform package', () => {
  const spec = launcher.packageSpecFor('darwin', 'arm64');
  assert.equal(spec.releaseAsset, 'olb-macos-arm64');
  assert.equal(spec.binaryPath, 'bin/olb');
});

test('resolveBinaryPath accepts explicit override', () => {
  assert.equal(launcher.resolveBinaryPath({ binaryPath: '/tmp/olb' }), '/tmp/olb');
});

test('packageSpecFor rejects unsupported platform', () => {
  assert.throws(() => launcher.packageSpecFor('linux', 'arm64'), /unsupported platform/);
});
