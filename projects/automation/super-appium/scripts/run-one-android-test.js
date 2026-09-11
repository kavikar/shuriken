#!/usr/bin/env node
"use strict";

const { remote } = require("webdriverio");
const { execFileSync } = require("child_process");

function detectUdId() {
  if (process.env.APPIUM_TEST_UDID) {
    return process.env.APPIUM_TEST_UDID;
  }

  const adb = process.env.ADB_PATH || "adb";
  const output = execFileSync(adb, ["devices", "-l"], { encoding: "utf8" });
  const lines = output.split(/\r?\n/);

  for (const line of lines) {
    const match = line.match(/^(.+?)\s+device\b/);
    if (match) {
      return match[1].trim();
    }
  }

  return null;
}

async function main() {
  const deviceName = process.env.APPIUM_DEVICE_NAME || "Android Device";
  const udid = detectUdId();
  const appPackage = process.env.APPIUM_TEST_PACKAGE || "com.android.settings";
  const appActivity = process.env.APPIUM_TEST_ACTIVITY || ".Settings";
  const serverUrl = process.env.APPIUM_SERVER_URL || "http://127.0.0.1:4723";

  const capabilities = {
    platformName: "Android",
    "appium:automationName": "UiAutomator2",
    "appium:deviceName": deviceName,
    "appium:udid": udid,
    "appium:appPackage": appPackage,
    "appium:appActivity": appActivity,
    "appium:noReset": true,
    "appium:newCommandTimeout": 180
  };

  const client = await remote({
    hostname: "127.0.0.1",
    port: 4723,
    path: "/",
    logLevel: "info",
    capabilities
  });

  try {
    const title = await client.getPageSource();
    console.log("[PASS] Session started");
    console.log(`[INFO] Page source length: ${title.length}`);

    const screenshot = await client.takeScreenshot();
    console.log(`[INFO] Screenshot captured (${screenshot.length} base64 chars)`);

    console.log(`[INFO] Tested package: ${appPackage}`);
    console.log(`[INFO] Tested activity: ${appActivity}`);
    console.log("SUMMARY: PASS");
  } catch (error) {
    console.error("SUMMARY: FAIL");
    console.error(`ISSUE: ${error.message}`);
    process.exitCode = 1;
  } finally {
    await client.deleteSession();
  }
}

main().catch((error) => {
  console.error("SUMMARY: FAIL");
  console.error(`ISSUE: ${error.message}`);
  process.exit(1);
});
