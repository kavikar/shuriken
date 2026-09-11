import fs from 'node:fs/promises';
import path from 'node:path';

function readArg(args: string[], flag: string): string | undefined {
  const idx = args.indexOf(flag);
  if (idx === -1) return undefined;
  return args[idx + 1];
}

function toStamp(date = new Date()): string {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  const dd = String(date.getDate()).padStart(2, '0');
  const hh = String(date.getHours()).padStart(2, '0');
  const mi = String(date.getMinutes()).padStart(2, '0');
  const ss = String(date.getSeconds()).padStart(2, '0');
  return `${yyyy}${mm}${dd}-${hh}${mi}${ss}`;
}

async function moveSafely(fromPath: string, toPath: string): Promise<void> {
  await fs.mkdir(path.dirname(toPath), { recursive: true });
  await fs.rename(fromPath, toPath);
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const baseDir = path.resolve(readArg(args, '--base-dir') || './reports/brand4/loyalty-adapter');
  const keep = Number(readArg(args, '--keep') || '2');

  if (!Number.isInteger(keep) || keep < 1) {
    throw new Error('Invalid --keep value. Must be an integer >= 1.');
  }

  const entries = await fs.readdir(baseDir, { withFileTypes: true });
  const runs = entries
    .filter((e) => e.isDirectory() && e.name.startsWith('newman-epsilon-open-'))
    .map((e) => e.name)
    .sort((a, b) => b.localeCompare(a));

  const toArchive = runs.slice(keep);
  if (toArchive.length === 0) {
    process.stdout.write(`No cleanup needed. Keeping latest ${keep} run(s).\n`);
    return;
  }

  const archiveRoot = path.join(baseDir, `archive-${toStamp()}`);
  await fs.mkdir(archiveRoot, { recursive: true });

  for (const dirName of toArchive) {
    const fromPath = path.join(baseDir, dirName);
    const toPath = path.join(archiveRoot, dirName);
    await moveSafely(fromPath, toPath);
    process.stdout.write(`Archived: ${dirName}\n`);
  }

  process.stdout.write(`Archive folder: ${archiveRoot}\n`);
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
