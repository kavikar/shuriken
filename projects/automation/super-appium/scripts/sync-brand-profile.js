#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i++) {
    const key = argv[i];
    const next = argv[i + 1];
    if (key.startsWith("--")) {
      args[key.slice(2)] = next && !next.startsWith("--") ? next : "true";
      if (next && !next.startsWith("--")) i++;
    }
  }
  return args;
}

function required(value, name) {
  if (!value) {
    throw new Error(`Missing required argument: --${name}`);
  }
}

function pick(obj, key, fallback = "") {
  const value = obj[key];
  return value === undefined || value === null ? fallback : String(value);
}

function main() {
  const args = parseArgs(process.argv);
  const brand = args.brand || "brand3";
  const envName = args.env || "uat";
  const sourceRoot =
    args.sourceRoot ||
    process.env.PROFILE_ROOT ||
    "profiles";
  const outPath = args.out || "artifacts/runtime/brand-profile.json";

  required(brand, "brand");
  required(envName, "env");

  const sourceFile = path.resolve(sourceRoot, brand, `maestro.${envName}.json`);
  if (!fs.existsSync(sourceFile)) {
    throw new Error(`Brand profile not found: ${sourceFile}`);
  }

  const raw = JSON.parse(fs.readFileSync(sourceFile, "utf8"));
  const env = raw.env || {};
  const thresholds = raw.thresholds || {};

  const profile = {
    sourceFile,
    brand,
    env: envName,
    generatedAt: new Date().toISOString(),
    app: {
      iosBundleId: pick(env, "IOS_BUNDLE_ID"),
      androidBundleId: pick(env, "ANDROID_BUNDLE_ID"),
      engineBrand: pick(env, "ENGINE_BRAND", brand)
    },
    commerce: {
      locationQuery: pick(env, "LOCATION_QUERY"),
      locationId: pick(env, "LOCATION_ID"),
      fulfillmentType: pick(env, "FULFILLMENT_TYPE"),
      categoryName: pick(env, "CATEGORY_NAME"),
      productName: pick(env, "PRODUCT_NAME")
    },
    endpoints: {
      apiEndpoint: pick(env, "API_ENDPOINT"),
      notificationServiceUrl: pick(env, "NOTIFICATION_SERVICE_URL")
    },
    thresholds,
    secretKeysPresent: {
      authEmail: Boolean(env.AUTH_EMAIL),
      authPass: Boolean(env.AUTH_PASS),
      ccNumber: Boolean(env.CC_NUMBER),
      ccCvv: Boolean(env.CC_CVV),
      ccExp: Boolean(env.CC_EXP),
      ccZip: Boolean(env.CC_ZIP)
    }
  };

  const fullOutPath = path.resolve(outPath);
  fs.mkdirSync(path.dirname(fullOutPath), { recursive: true });
  fs.writeFileSync(fullOutPath, JSON.stringify(profile, null, 2), "utf8");

  process.stdout.write(`${fullOutPath}\n`);
}

try {
  main();
} catch (error) {
  process.stderr.write(`sync-brand-profile failed: ${error.message}\n`);
  process.exit(1);
}
