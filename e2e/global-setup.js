import { chromium } from "@playwright/test";

export default async function globalSetup() {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.goto("http://127.0.0.1:5173/register");
    await page.getByLabel("Email address").waitFor({ state: "visible" });
  } finally {
    await browser.close();
  }
}
