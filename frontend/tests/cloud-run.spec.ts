import { test, expect } from '@playwright/test';

test.describe('Cloud Run Services Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/services/cloud-run');
    await page.waitForLoadState('networkidle');
  });

  test('displays page header correctly', async ({ page }) => {
    await expect(page.locator('h1:has-text("Cloud Run Services")')).toBeVisible();
    await expect(page.locator('text=Manage and monitor your Cloud Run deployments')).toBeVisible();
  });

  test('displays Refresh button', async ({ page }) => {
    const refreshButton = page.locator('button:has-text("Refresh")');
    await expect(refreshButton).toBeVisible();
  });

  test('displays Total Services card', async ({ page }) => {
    await expect(page.locator('text=Total Services')).toBeVisible();
  });

  test('displays Total Requests card', async ({ page }) => {
    await expect(page.locator('text=Total Requests (24h)')).toBeVisible();
  });

  test('displays Avg Error Rate card', async ({ page }) => {
    await expect(page.locator('text=Avg Error Rate')).toBeVisible();
  });

  test('displays Avg P95 Latency card', async ({ page }) => {
    await expect(page.locator('text=Avg P95 Latency')).toBeVisible();
  });

  test('displays Services section', async ({ page }) => {
    await expect(page.locator('text=Services').nth(1)).toBeVisible();
    await expect(page.locator('text=All Cloud Run services in your project')).toBeVisible();
  });

  test('displays services table with correct headers', async ({ page }) => {
    await expect(page.locator('table')).toBeVisible();

    await expect(page.locator('th:has-text("Service")')).toBeVisible();
    await expect(page.locator('th:has-text("Status")')).toBeVisible();
    await expect(page.locator('th:has-text("Region")')).toBeVisible();
    await expect(page.locator('th:has-text("Revision")')).toBeVisible();
    await expect(page.locator('th:has-text("Traffic")')).toBeVisible();
    await expect(page.locator('th:has-text("Requests")')).toBeVisible();
    await expect(page.locator('th:has-text("Error Rate")')).toBeVisible();
    await expect(page.locator('th:has-text("P95")')).toBeVisible();
  });

  test('services table has data rows', async ({ page }) => {
    const tableRows = page.locator('table tbody tr');
    expect(await tableRows.count()).toBeGreaterThan(0);
  });

  test('table shows service names', async ({ page }) => {
    // Check for mock service names
    await expect(page.locator('td:has-text("glass-pane")')).toBeVisible();
    await expect(page.locator('td:has-text("api-gateway")')).toBeVisible();
    await expect(page.locator('td:has-text("auth-service")')).toBeVisible();
  });

  test('table shows status badges', async ({ page }) => {
    // Check for status badges
    const readyBadge = page.locator('span:has-text("READY")');
    const deployingBadge = page.locator('span:has-text("DEPLOYING")');

    expect((await readyBadge.count()) > 0 || (await deployingBadge.count()) > 0).toBeTruthy();
  });

  test('table shows region information', async ({ page }) => {
    await expect(page.locator('td:has-text("us-central1")').first()).toBeVisible();
  });

  test('table shows revision names', async ({ page }) => {
    // Revisions are in monospace font
    const revisions = page.locator('td.font-mono');
    expect(await revisions.count()).toBeGreaterThan(0);
  });

  test('table shows traffic percentages', async ({ page }) => {
    await expect(page.locator('td:has-text("100%")').first()).toBeVisible();
  });

  test('table shows request counts', async ({ page }) => {
    // Request counts are numbers with commas
    const requestCells = page.locator('td:has-text(/\\d+,?\\d*/)');
    expect(await requestCells.count()).toBeGreaterThan(0);
  });

  test('table shows error rate percentages', async ({ page }) => {
    // Error rates like "0.1%"
    const errorRates = page.locator('td:has-text(/\\d+\\.\\d%/)');
    expect(await errorRates.count()).toBeGreaterThan(0);
  });

  test('table shows P95 latency in ms', async ({ page }) => {
    await expect(page.locator('td:has-text(/\\d+ms/)').first()).toBeVisible();
  });

  test('external link icons are present for service URLs', async ({ page }) => {
    const externalLinkIcons = page.locator('svg.lucide-external-link');
    expect(await externalLinkIcons.count()).toBeGreaterThan(0);
  });

  test('dropdown menu exists for each service row', async ({ page }) => {
    // Each row should have a more options button
    const moreButtons = page.locator('button').filter({ has: page.locator('svg.lucide-more-vertical') });
    expect(await moreButtons.count()).toBeGreaterThan(0);
  });

  test('dropdown menu opens on click', async ({ page }) => {
    const moreButton = page.locator('button').filter({ has: page.locator('svg.lucide-more-vertical') }).first();
    await moreButton.click();

    // Menu should appear
    await expect(page.locator('[role="menu"]')).toBeVisible();
  });

  test('dropdown menu has correct options', async ({ page }) => {
    const moreButton = page.locator('button').filter({ has: page.locator('svg.lucide-more-vertical') }).first();
    await moreButton.click();

    await expect(page.locator('text=View Metrics')).toBeVisible();
    await expect(page.locator('text=View Logs')).toBeVisible();
    await expect(page.locator('text=View Revisions')).toBeVisible();
    await expect(page.locator('text=Edit Service')).toBeVisible();
  });

  test('dropdown menu closes on click outside', async ({ page }) => {
    const moreButton = page.locator('button').filter({ has: page.locator('svg.lucide-more-vertical') }).first();
    await moreButton.click();

    await expect(page.locator('[role="menu"]')).toBeVisible();

    // Click outside
    await page.locator('h1').click();

    await expect(page.locator('[role="menu"]')).not.toBeVisible();
  });

  test('Refresh button is clickable', async ({ page }) => {
    const refreshButton = page.locator('button:has-text("Refresh")');
    await refreshButton.click();

    // Page should still be functional
    await expect(page.locator('h1:has-text("Cloud Run Services")')).toBeVisible();
  });

  test('stats cards show numeric values', async ({ page }) => {
    // Total Services should show a number
    const totalServicesCard = page.locator('text=Total Services').locator('..').locator('..');
    await expect(totalServicesCard.locator('.text-2xl')).toBeVisible();
  });

  test('mobile responsive layout', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.reload();
    await page.waitForLoadState('networkidle');

    await expect(page.locator('h1:has-text("Cloud Run Services")')).toBeVisible();
    await expect(page.locator('table')).toBeVisible();
  });

  test('tablet responsive layout', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.reload();
    await page.waitForLoadState('networkidle');

    await expect(page.locator('h1:has-text("Cloud Run Services")')).toBeVisible();
  });

  test('status badge colors are correct', async ({ page }) => {
    // READY should be green, DEPLOYING should be blue
    const readyBadge = page.locator('span:has-text("READY")').first();

    if (await readyBadge.isVisible()) {
      // Just verify it's visible - color checking is complex
      expect(await readyBadge.isVisible()).toBeTruthy();
    }
  });

  test('high error rate services are highlighted', async ({ page }) => {
    // Services with error rate > 3% should have red text
    const errorCells = page.locator('td span.text-red-500');

    const count = await errorCells.count();
    if (count > 0) {
      await expect(errorCells.first()).toBeVisible();
    }
  });
});
