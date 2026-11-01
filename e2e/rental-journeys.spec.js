import { expect, test } from "@playwright/test";

const password = "RentalTest123!";
const png = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGPQrYgCAAHVAQB4vNrgAAAAAElFTkSuQmCC",
  "base64",
);

async function registerAndLogin(page, { email, name, role }) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill(name);
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Account type").selectOption(role);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(
    role === "landlord" ? /\/manage\/properties$/ : /\/tenant\/details$/,
  );
}

test("landlord listing and tenant contact/application journey", async ({
  browser,
  page: landlordPage,
}) => {
  const uniqueId = `${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`;
  const propertyName = `E2E Home ${uniqueId}`;
  const landlordEmail = `landlord-${uniqueId}@example.test`;
  const tenantEmail = `tenant-${uniqueId}@example.test`;

  await registerAndLogin(landlordPage, {
    email: landlordEmail,
    name: "E2E Landlord",
    role: "landlord",
  });

  await landlordPage.getByRole("button", { name: "Add property" }).click();
  const dialog = landlordPage.getByRole("dialog");
  await dialog.getByLabel("Name *").fill(propertyName);
  await dialog.getByLabel("Address line *").fill("1 Test Street");
  await dialog.getByLabel("City *").fill("Nairobi");
  await dialog.getByLabel("Property photos *").setInputFiles([
    { name: "front.png", mimeType: "image/png", buffer: png },
    { name: "living-room.png", mimeType: "image/png", buffer: png },
  ]);
  await dialog.getByLabel("Unit number *").fill("A1");
  await dialog.getByLabel("Unit type *").selectOption("two-bedroom");
  await dialog.getByLabel("Bedrooms *").fill("2");
  await dialog.getByLabel("Bathrooms *").fill("1");
  const rentInput = dialog.getByLabel(/Monthly rent/);
  await rentInput.fill("0");
  expect(
    await rentInput.evaluate((input) => input.validity.rangeUnderflow),
  ).toBe(true);
  await rentInput.fill("25000");

  const createPropertyResponse = landlordPage.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/properties",
  );
  await dialog.getByRole("button", { name: "Add property" }).click();
  const propertyResponse = await createPropertyResponse;
  expect(propertyResponse.status()).toBe(201);
  const propertyId = (await propertyResponse.json()).property.id;
  await expect(dialog).toBeHidden();
  await expect(landlordPage.getByText(propertyName)).toBeVisible();
  let photoRequestCount = 0;
  await landlordPage.route("**/api/public/photos/**", async (route) => {
    photoRequestCount += 1;
    if (photoRequestCount === 1) {
      await route.fulfill({ status: 404, body: "missing test image" });
    } else {
      await route.continue();
    }
  });
  await landlordPage.goto(`/properties/${propertyId}`);
  await expect(landlordPage.locator(".listing-photo")).toHaveCount(2);
  await expect(landlordPage.locator(".listing-image-unavailable")).toHaveCount(1);

  const tenantContext = await browser.newContext();
  const tenantPage = await tenantContext.newPage();
  try {
    await registerAndLogin(tenantPage, {
      email: tenantEmail,
      name: "E2E Tenant",
      role: "tenant",
    });

    await tenantPage.goto(`/properties/${propertyId}`);
    await tenantPage.getByLabel("Your message").fill("Is a viewing available?");
    await tenantPage.getByRole("button", { name: "Message landlord" }).click();
    await expect(tenantPage).toHaveURL(/\/messages\?conversation=/);

    await tenantPage.locator(".app-account-menu summary").click();
    await tenantPage.getByRole("button", { name: "Sign out" }).click();
    await tenantPage.goto(`/properties/${propertyId}`);
    await tenantPage.getByRole("link", { name: "Sign in to apply" }).click();
    await tenantPage.getByLabel("Email address").fill(tenantEmail);
    await tenantPage.getByLabel("Password", { exact: true }).fill(password);
    await tenantPage.getByRole("button", { name: "Log in" }).click();
    await expect(tenantPage).toHaveURL(new RegExp(`/properties/${propertyId}`));
    await expect(tenantPage.getByRole("heading", { name: "Apply for unit A1" })).toBeVisible();
    await expect(tenantPage.getByText("Complete your tenant profile before applying.")).toBeVisible();
    await expect(tenantPage.getByRole("button", { name: "Next" })).toBeDisabled();
    await tenantPage.getByRole("link", { name: "Review or complete my profile" }).click();

    await tenantPage.locator('[name="phone"]').fill("+254712345678");
    await tenantPage.locator('[name="employment_status"]').selectOption("employed");
    await tenantPage.locator('[name="emergency_contact_name"]').fill("E2E Contact");
    await tenantPage.locator('[name="emergency_contact_phone"]').fill("+254711111111");
    await tenantPage.locator('[name="emergency_contact_relationship"]').fill("Sibling");
    await tenantPage.getByRole("button", { name: "Create profile" }).click();
    await expect(tenantPage.getByRole("status")).toContainText("Your profile has been saved.");
    await tenantPage.getByLabel("Upload ID photo").setInputFiles({
      name: "identity.png",
      mimeType: "image/png",
      buffer: png,
    });
    await expect(tenantPage.getByRole("status")).toContainText(
      "Document uploaded securely.",
    );

    await tenantPage.goto(`/properties/${propertyId}`);
    await tenantPage.getByRole("button", { name: "Apply" }).click();
    await tenantPage.getByRole("button", { name: "Next" }).click();
    await expect(tenantPage.getByText(
      "Documents already in your profile are included automatically. Add another only if you need to.",
    )).toBeVisible();
    await expect(
      tenantPage.getByLabel("Add another document (optional)"),
    ).toBeVisible();
    await tenantPage.getByRole("button", { name: "Next" }).click();
    const moveInDate = new Date(Date.now() + 45 * 24 * 60 * 60 * 1000)
      .toISOString()
      .slice(0, 10);
    await tenantPage.getByLabel("Requested move-in date").fill(moveInDate);
    await tenantPage.getByRole("button", { name: "Next" }).click();
    await tenantPage.getByRole("button", { name: "Submit application" }).click();
    await expect(tenantPage.getByRole("status")).toContainText("Application submitted");

    await landlordPage.goto("/manage/applications");
    const application = landlordPage.locator(".manage-list > li").filter({
      hasText: tenantEmail,
    });
    await expect(application).toBeVisible();
    await application.getByText("Applicant profile snapshot").click();
    await expect(application.getByText("identity · 1 KB")).toBeVisible();
    await application.getByText("Applicant profile snapshot").click();
    await application.getByRole("button", { name: "Approve" }).click();
    await application.getByRole("button", { name: "Confirm approved" }).click();
    const reason = application.getByLabel("Reason for approved");
    expect(await reason.evaluate((input) => input.validity.valueMissing)).toBe(true);
    await reason.fill("The requested move-in date is available.");
    await application.getByRole("button", { name: "Confirm approved" }).click();
    await expect(application.locator(".manage-badge")).toHaveText("approved");
  } finally {
    await tenantContext.close();
  }
});

test("duplicate registration displays an actionable error", async ({ page }) => {
  const uniqueId = `${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`;
  const email = `duplicate-${uniqueId}@example.test`;
  await page.goto("/register");
  await page.getByLabel("Full name").fill("First Registration");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.goto("/register");
  await page.getByLabel("Full name").fill("Duplicate Registration");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "A user with this email already exists",
  );
});

test("temporary account API failures remain recoverable and mobile navigation works", async ({
  page,
}) => {
  const uniqueId = `${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`;
  await registerAndLogin(page, {
    email: `account-retry-${uniqueId}@example.test`,
    name: "Retry Landlord",
    role: "landlord",
  });

  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: "Temporary account service outage." }),
    }),
  );
  await page.goto("/manage/properties");
  await expect(page.locator(".app-request-error")).toContainText(
    "Temporary account service outage.",
  );
  expect(
    await page.evaluate(() => localStorage.getItem("access_token")),
  ).toBeTruthy();

  await page.unroute("**/api/auth/me");
  await page.locator(".app-request-error").getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("button", { name: "Add property" })).toBeVisible();
  await page.locator(".app-account-status").getByRole("button", { name: "Try again" }).click();
  await expect(page.locator(".app-account-menu")).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.locator(".app-workspace").evaluate((element) =>
      getComputedStyle(element).display,
    ),
  ).toBe("block");
  expect(
    await page.locator(".app-sidebar").evaluate((element) =>
      getComputedStyle(element).position,
    ),
  ).toBe("sticky");
});
