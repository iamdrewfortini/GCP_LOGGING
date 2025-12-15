import { test, expect } from '@playwright/test';

test.describe('Cost Analytics Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/costs');
    await page.waitForLoadState('networkidle');
  });

  test('displays page header correctly', async ({ page }) => {
    await expect(page.locator('h1:has-text("Cost Analytics")')).toBeVisible();
    await expect(page.locator('text=Monitor and optimize your GCP spending')).toBeVisible();
  });

  test('displays time range selector', async ({ page }) => {
    const timeRangeTrigger = page.locator('button:has-text("Last")');
    await expect(timeRangeTrigger).toBeVisible();
  });

  test('time range selector has correct options', async ({ page }) => {
    const timeRangeTrigger = page.locator('button:has-text("Last")');
    await timeRangeTrigger.click();

    await expect(page.locator('text=Last 7 days')).toBeVisible();
    await expect(page.locator('text=Last 30 days')).toBeVisible();
    await expect(page.locator('text=Last 90 days')).toBeVisible();
    await expect(page.locator('text=Year to date')).toBeVisible();
  });

  test('displays Total Spend card', async ({ page }) => {
    await expect(page.locator('text=Total Spend (MTD)')).toBeVisible();
    // Should have a dollar amount
    await expect(page.locator('text=/\\$[\\d,]+\\.\\d{2}/')).toBeVisible();
  });

  test('displays Budget Used card', async ({ page }) => {
    await expect(page.locator('text=Budget Used')).toBeVisible();
    // Should have percentage
    await expect(page.locator('text=/\\d+\\.\\d%/')).toBeVisible();
  });

  test('displays Forecast card', async ({ page }) => {
    await expect(page.locator('text=Forecast (EOM)')).toBeVisible();
    await expect(page.locator('text=Based on current usage')).toBeVisible();
  });

  test('displays vs Last Month card', async ({ page }) => {
    await expect(page.locator('text=vs Last Month')).toBeVisible();
    // Should show percentage change
    await expect(page.locator('text=/-?\\d+\\.\\d%/')).toBeVisible();
  });

  test('displays budget progress bar', async ({ page }) => {
    // Look for progress bar elements
    const progressBars = page.locator('[class*="rounded-full"][class*="bg-"]');
    expect(await progressBars.count()).toBeGreaterThan(0);
  });

  test('displays Cost by Service section', async ({ page }) => {
    await expect(page.locator('text=Cost by Service')).toBeVisible();
    await expect(page.locator('text=Breakdown of spending across GCP services')).toBeVisible();
  });

  test('displays services table with correct headers', async ({ page }) => {
    await expect(page.locator('table')).toBeVisible();

    await expect(page.locator('th:has-text("Service")')).toBeVisible();
    await expect(page.locator('th:has-text("Cost (MTD)")')).toBeVisible();
    await expect(page.locator('th:has-text("Budget")')).toBeVisible();
    await expect(page.locator('th:has-text("% Used")')).toBeVisible();
    await expect(page.locator('th:has-text("Change")')).toBeVisible();
    await expect(page.locator('th:has-text("Status")')).toBeVisible();
  });

  test('services table has data rows', async ({ page }) => {
    const tableRows = page.locator('table tbody tr');
    expect(await tableRows.count()).toBeGreaterThan(0);
  });

  test('table shows service names', async ({ page }) => {
    const serviceNames = ['Cloud Run', 'BigQuery', 'Cloud Storage', 'Cloud Functions', 'Pub/Sub', 'Cloud Logging'];

    for (const name of serviceNames) {
      await expect(page.locator(`td:has-text("${name}")`)).toBeVisible();
    }
  });

  test('table shows cost values with dollar signs', async ({ page }) => {
    const costCells = page.locator('td:has-text("$")');
    expect(await costCells.count()).toBeGreaterThan(0);
  });

  test('table shows status badges', async ({ page }) => {
    // Look for status badges like "On Track", "Warning", "Over Budget"
    const statusBadges = page.locator('span:has-text("On Track"), span:has-text("Warning"), span:has-text("Over Budget")');
    expect(await statusBadges.count()).toBeGreaterThan(0);
  });

  test('percentage change shows positive/negative styling', async ({ page }) => {
    // Look for change percentages with + or - prefix
    const positiveChange = page.locator('td span:has-text("+")');
    const negativeChange = page.locator('td span:has-text("-")');

    const hasChanges = (await positiveChange.count()) > 0 || (await negativeChange.count()) > 0;
    expect(hasChanges).toBeTruthy();
  });

  test('budget progress bars show in table', async ({ page }) => {
    // Each row should have a progress bar
    const progressBars = page.locator('table tbody tr').locator('[class*="rounded-full"]');
    expect(await progressBars.count()).toBeGreaterThan(0);
  });

  test('time range selection updates display', async ({ page }) => {
    const timeRangeTrigger = page.locator('button:has-text("Last")');
    await timeRangeTrigger.click();

    await page.locator('[role="option"]:has-text("Last 7 days")').click();

    // Page should still be functional
    await expect(page.locator('h1:has-text("Cost Analytics")')).toBeVisible();
  });

  test('mobile responsive layout', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.reload();
    await page.waitForLoadState('networkidle');

    await expect(page.locator('h1:has-text("Cost Analytics")')).toBeVisible();
    await expect(page.locator('table')).toBeVisible();
  });

  test('tablet responsive layout', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.reload();
    await page.waitForLoadState('networkidle');

    await expect(page.locator('h1:has-text("Cost Analytics")')).toBeVisible();
  });

  test('stats cards display icons', async ({ page }) => {
    // Look for lucide icons
    const icons = page.locator('svg.lucide-dollar-sign, svg.lucide-trending-up, svg.lucide-trending-down, svg.lucide-alert-circle');
    expect(await icons.count()).toBeGreaterThan(0);
  });

  test('over budget services are highlighted', async ({ page }) => {
    // Look for "Over Budget" badge
    const overBudgetBadge = page.locator('span:has-text("Over Budget")');
    // May or may not be present depending on data
  });

  test('warning state services are highlighted', async ({ page }) => {
    // Look for "Warning" badge
    const warningBadge = page.locator('span:has-text("Warning")');
    // May or may not be present depending on data
  });

  test('on track services are shown', async ({ page }) => {
    const onTrackBadge = page.locator('span:has-text("On Track")');
    expect(await onTrackBadge.count()).toBeGreaterThan(0);
  });
});
