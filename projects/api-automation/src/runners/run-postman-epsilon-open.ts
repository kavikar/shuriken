import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';

interface CliArgs {
  collectionPath: string;
  env: string;
  environmentFile?: string;
  baseUrl: string;
  brand: string;
  lmsProfileId: string;
  transactionId: string;
  reportDir: string;
}

type PostmanItem = {
  name?: string;
  item?: PostmanItem[];
};

type PostmanCollection = {
  info?: {
    name?: string;
  };
  item?: PostmanItem[];
  [key: string]: unknown;
};

function readArg(args: string[], flag: string): string | undefined {
  const index = args.findIndex((entry) => entry === flag);
  if (index === -1 || !args[index + 1]) {
    return undefined;
  }

  return args[index + 1];
}

function buildArgs(argv: string[]): CliArgs {
  const env = (readArg(argv, '--env') || 'qa').toLowerCase();

  const defaultBaseUrl =
    env === 'uat'
      ? 'https://loyalty-adapter-v0.b4-api.uat.staging.example'
      : 'https://loyalty-adapter-v0.b4-api.qa.staging.example';

  const defaultLmsProfileId =
    env === 'uat'
      ? '3ed48d62-9f50-4ea3-a974-a192d53c4f0e'
      : 'eba78af2-d472-4b47-ba2c-44abcccedd7d';

  const collectionPath = path.resolve(readArg(argv, '--collection') || './Planner-loyalty-adapter-postmanCollection.json');
  const environmentFile = readArg(argv, '--environment-file');
  const baseUrl = readArg(argv, '--base-url') || defaultBaseUrl;
  const brand = readArg(argv, '--brand') || 'B4';
  const lmsProfileId = readArg(argv, '--lms-profile-id') || defaultLmsProfileId;
  const transactionId = readArg(argv, '--transaction-id') || '';
  const reportDir = path.resolve(
    readArg(argv, '--report-dir') ||
      `./reports/brand4/loyalty-adapter/newman-epsilon-open-${env}-${new Date().toISOString().slice(0, 10)}`,
  );

  if (!transactionId) {
    throw new Error('Missing required --transaction-id value.');
  }

  return {
    collectionPath,
    env,
    environmentFile,
    baseUrl,
    brand,
    lmsProfileId,
    transactionId,
    reportDir,
  };
}

function isRequestNameInOpenFlow(name: string): boolean {
  const match = /^(\d+)_/.exec(name.trim());
  if (!match) {
    return false;
  }

  const sequence = Number(match[1]);
  return Number.isInteger(sequence) && sequence >= 1 && sequence <= 19;
}

function filterEpsilonOpenCollection(collection: PostmanCollection): PostmanCollection {
  const topLevelItems = collection.item || [];
  const epsilonFolder = topLevelItems.find((entry) => (entry.name || '').includes('brand4EpsilonCircuit'));

  if (!epsilonFolder || !epsilonFolder.item) {
    throw new Error('Could not find brand4EpsilonCircuit folder in collection.');
  }

  const filteredItems = epsilonFolder.item.filter((entry) => {
    const name = entry.name || '';
    return isRequestNameInOpenFlow(name);
  });

  if (filteredItems.length !== 14) {
    throw new Error(`Expected 14 requests (valid-only open cases + reset), found ${filteredItems.length}.`);
  }

  return {
    ...collection,
    info: {
      ...(collection.info || {}),
      name: `${collection.info?.name || 'Collection'} [Automated Epsilon Open 1-19]`,
    },
    item: [
      {
        ...epsilonFolder,
        item: filteredItems,
      },
    ],
  };
}

async function runNewman(commandArgs: string[]): Promise<number> {
  return new Promise((resolve, reject) => {
    const processRef = spawn('npx', commandArgs, {
      shell: true,
      stdio: 'inherit',
    });

    processRef.on('error', (error) => reject(error));
    processRef.on('exit', (code) => resolve(code ?? 1));
  });
}

async function main(): Promise<void> {
  const args = buildArgs(process.argv.slice(2));
  await fs.mkdir(args.reportDir, { recursive: true });

  const environmentCandidates = args.environmentFile
    ? [path.resolve(args.environmentFile)]
    : [
        path.resolve(`./environments/brand4-loyalty-${args.env}.postman_environment.json`),
        path.resolve(`./environments/brand4-loyalty.${args.env}.postman_environment.json`),
      ];

  let selectedEnvironmentFile = environmentCandidates[0];
  let hasEnvironmentFile = false;
  for (const candidate of environmentCandidates) {
    try {
      await fs.access(candidate);
      selectedEnvironmentFile = candidate;
      hasEnvironmentFile = true;
      break;
    } catch {
      // Continue to next candidate.
    }
  }

  const sourceText = await fs.readFile(args.collectionPath, 'utf8');
  const sourceCollection = JSON.parse(sourceText) as PostmanCollection;
  const filteredCollection = filterEpsilonOpenCollection(sourceCollection);

  const filteredCollectionPath = path.join(args.reportDir, 'epsilon-open-only.postman_collection.json');
  const jsonReportPath = path.join(args.reportDir, 'newman-report.json');
  const junitReportPath = path.join(args.reportDir, 'newman-report.xml');
  const htmlReportPath = path.join(args.reportDir, 'newman-htmlextra-report.html');
  await fs.writeFile(filteredCollectionPath, JSON.stringify(filteredCollection, null, 2), 'utf8');

  const newmanArgs = [
    'newman',
    'run',
    filteredCollectionPath,
    '--reporters',
    'cli,json,junit,htmlextra',
    '--reporter-json-export',
    jsonReportPath,
    '--reporter-junit-export',
    junitReportPath,
    '--reporter-htmlextra-export',
    htmlReportPath,
    '--reporter-htmlextra-title',
    'Brand Four Loyalty Epsilon Circuit Open Report',
    '--reporter-htmlextra-logs',
    '--reporter-htmlextra-showEnvironmentData',
    '--reporter-htmlextra-showMarkdownLinks',
    ...(hasEnvironmentFile ? ['--environment', selectedEnvironmentFile] : []),
    '--env-var',
    `baseUrl=${args.baseUrl}`,
    '--env-var',
    `brand=${args.brand}`,
    '--env-var',
    `lmsProfileId=${args.lmsProfileId}`,
    '--env-var',
    `transactionId=${args.transactionId}`,
  ];

  const exitCode = await runNewman(newmanArgs);
  process.stdout.write(
    [
      `Postman run completed. Reports folder: ${args.reportDir}`,
      `- Env preset: ${args.env.toUpperCase()}`,
      `- Environment file: ${hasEnvironmentFile ? selectedEnvironmentFile : 'not found (using --env-var overrides only)'}`,
      `- JSON: ${jsonReportPath}`,
      `- JUnit: ${junitReportPath}`,
      `- HTML (Extent-like): ${htmlReportPath}`,
    ].join('\n') + '\n',
  );

  if (exitCode !== 0) {
    throw new Error(`Newman execution failed with exit code ${exitCode}.`);
  }
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
