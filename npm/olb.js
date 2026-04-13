#!/usr/bin/env node

const { spawnSync } = require('node:child_process');
const { existsSync } = require('node:fs');
const path = require('node:path');

const repoUrl = 'https://github.com/duanluan/openai-local-bridge.git';
const packageRoot = path.resolve(__dirname, '..');
const packageRef = resolvePackageRef();
const args = process.argv.slice(2);

function normalizePackageRef(value) {
  return value.trim().replace(/[`'"]/g, '').replace(/\s+/g, '');
}

function resolvePackageRef() {
  if (existsSync(path.join(packageRoot, 'pyproject.toml'))) {
    return packageRoot;
  }
  return normalizePackageRef(`git+${repoUrl}`);
}

function hasCommand(command) {
  const probe = process.platform === 'win32' ? 'where' : 'command';
  const probeArgs = process.platform === 'win32' ? [command] : ['-v', command];
  const result = spawnSync(probe, probeArgs, { stdio: 'ignore', shell: process.platform !== 'win32' });
  return result.status === 0;
}

function run(command, commandArgs) {
  const result = spawnSync(command, commandArgs, { stdio: 'inherit' });
  if (result.error) {
    return { status: 1, error: result.error };
  }
  return { status: result.status ?? 1 };
}

function runPythonFlow(pythonCommand) {
  const pipResult = run(pythonCommand, ['-m', 'pip', 'install', '--user', '--upgrade', packageRef]);
  if (pipResult.status !== 0) {
    process.exit(pipResult.status);
  }

  const cliResult = run(pythonCommand, ['-m', 'olb_cli', ...args]);
  process.exit(cliResult.status);
}

if (hasCommand('uv')) {
  const uvResult = run('uv', ['tool', 'run', '--from', packageRef, 'olb', ...args]);
  process.exit(uvResult.status);
}

for (const pythonCommand of process.platform === 'win32' ? ['py', 'python'] : ['python3', 'python']) {
  if (hasCommand(pythonCommand)) {
    runPythonFlow(pythonCommand);
  }
}

console.error('missing command: uv, python3, or python');
process.exit(1);
