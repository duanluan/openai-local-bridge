#!/usr/bin/env node

const { spawnSync } = require('node:child_process');
const { existsSync } = require('node:fs');
const path = require('node:path');

const packageRoot = path.resolve(__dirname, '..');
const platformPackages = require('./platforms.json');

function platformKey(platform = process.platform, arch = process.arch) {
  return `${platform}-${arch}`;
}

function packageSpecFor(platform = process.platform, arch = process.arch) {
  const spec = platformPackages[platformKey(platform, arch)];
  if (!spec) {
    throw new Error(`unsupported platform: ${platform}/${arch}`);
  }
  return spec;
}

function resolveBinaryPath(options = {}) {
  const override = options.binaryPath || process.env.OLB_BINARY_PATH;
  if (override) {
    return override;
  }

  const spec = packageSpecFor(options.platform, options.arch);
  const binaryPath = path.join(packageRoot, 'npm', spec.binaryPath);
  if (!existsSync(binaryPath)) {
    throw new Error(`missing binary: ${binaryPath}; rerun npm install openai-local-bridge`);
  }
  return binaryPath;
}

function runBinary(binaryPath, args = process.argv.slice(2)) {
  const result = spawnSync(binaryPath, args, { stdio: 'inherit' });
  if (result.error) {
    throw result.error;
  }
  return result.status ?? 1;
}

function main(args = process.argv.slice(2)) {
  try {
    const binaryPath = resolveBinaryPath();
    process.exit(runBinary(binaryPath, args));
  } catch (error) {
    console.error(error.message || String(error));
    process.exit(1);
  }
}

module.exports = {
  packageSpecFor,
  platformKey,
  resolveBinaryPath,
  runBinary,
};

if (require.main === module) {
  main();
}
