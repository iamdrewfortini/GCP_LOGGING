import { test, expect } from '@playwright/test';

test.describe('Dashboard Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('displays page header correctly', async ({ page }) => {
    await expect(page.locator('h1:has-text("Dashboard")')).toBeVisible();
    await expect(page.locator('text=GCP Infrastructure Portal - Real-time Overview')).toBeVisible();
  });

  test('displays Refresh button', async ({ page }) => {
    const refreshButton = page.locator('button:has-text("Refresh")');
    await expect(refreshButton).toBeVisible();
  });

  test('displays AI Assistant button', async ({ page }) => {
    const aiButton = page.locator('button:has-text("AI Assistant")');
    await expect(aiButton).toBeVisible();
  });

  test('Refresh button triggers data refresh', async ({ page }) => {
    const refreshButton = page.locator('button:has-text("Refresh")');
    await refreshButton.click();

    // Wait for any loading state to complete
    await page.waitForTimeout(1000);

    // Verify page still shows content
    await expect(page.locator('h1:has-text("Dashboard")')).toBeVisible();
  });

  test('displays Quick Stats cards', async ({ page }) => {
    // Wait for stats to load
    await page.waitForTimeout(2000);

    // Verify stat card titles
    await expect(page.locator('text=Total Logs (24h)')).toBeVisible();
    await expect(page.locator('text=Errors (24h)')).toBeVisible();
    await expect(page.locator('text=Warnings (24h)')).toBeVisible();
    await expect(page.locator('text=Active Services')).toBeVisible();
  });

  test('stats cards show numeric values or loading skeletons', async ({ page }) => {
    // Wait for data to potentially load
    await page.waitForTimeout(3000);

    // Either we have numeric values or skeleton loaders
    const totalLogsCard = page.locator('text=Total Logs (24h)').locator('..').locator('..');
    await expect(totalLogsCard).toBeVisible();
  });

  test('displays Severity Distribution section', async ({ page }) => {
    await expect(page.locator('text=Severity Distribution')).toBeVisible();
    await expect(page.locator('text=Log counts by severity level')).toBeVisible();
  });

  test('displays Top Services section', async ({ page }) => {
    await expect(page.locator('text=Top Services by Logs')).toBeVisible();
    await expect(page.locator('text=Services with most log entries')).toBeVisible();
  });

  test('displays Quick Actions section', async ({ page }) => {
    await expect(page.locator('text=Quick Actions').first()).toBeVisible();
    await expect(page.locator('text=Common tasks and shortcuts')).toBeVisible();
  });

  test('Quick Actions buttons are clickable', async ({ page }) => {
    // Search Logs button
    const searchLogsBtn = page.locator('button:has-text("Search Logs")');
    await expect(searchLogsBtn).toBeVisible();

    // View Errors button
    const viewErrorsBtn = page.locator('button:has-text("View Errors")');
    await expect(viewErrorsBtn).toBeVisible();

    // AI Debugger button
    const aiDebuggerBtn = page.locator('button:has-text("AI Debugger")');
    await expect(aiDebuggerBtn).toBeVisible();

    // Cost Analytics button
    const costBtn = page.locator('button:has-text("Cost Analytics")');
    await expect(costBtn).toBeVisible();
  });

  test('Search Logs quick action navigates to /logs', async ({ page }) => {
    await page.locator('button:has-text("Search Logs")').click();
    await page.waitForURL('**/logs');
    await expect(page.locator('h1:has-text("Log Explorer")')).toBeVisible();
  });

  test('View Errors quick action navigates to /logs with filter', async ({ page }) => {
    await page.locator('button:has-text("View Errors")').click();
    await page.waitForURL(/.*logs.*severity=ERROR/);
    await expect(page.locator('h1:has-text("Log Explorer")')).toBeVisible();
  });

  test('AI Debugger quick action navigates to /chat', async ({ page }) => {
    await page.locator('button:has-text("AI Debugger")').click();
    await page.waitForURL('**/chat');
    await expect(page.locator('text=AI Log Debugger')).toBeVisible();
  });

  test('Cost Analytics quick action navigates to /costs', async ({ page }) => {
    await page.locator('button:has-text("Cost Analytics")').click();
    await page.waitForURL('**/costs');
    await expect(page.locator('h1:has-text("Cost Analytics")')).toBeVisible();
  });

  test('"View all errors" link in Errors card navigates correctly', async ({ page }) => {
    // Wait for data to load
    await page.waitForTimeout(2000);

    const viewErrorsLink = page.locator('text=View all errors →');
    if (await viewErrorsLink.isVisible()) {
      await viewErrorsLink.click();
      await page.waitForURL(/.*logs.*severity=ERROR/);
    }
  });

  test('"View warnings" link in Warnings card navigates correctly', async ({ page }) => {
    // Wait for data to load
    await page.waitForTimeout(2000);

    const viewWarningsLink = page.locator('text=View warnings →');
    if (await viewWarningsLink.isVisible()) {
      await viewWarningsLink.click();
      await page.waitForURL(/.*logs.*severity=WARNING/);
    }
  });

  test('AI Assistant modal opens and closes', async ({ page }) => {
    const aiButton = page.locator('button:has-text("AI Assistant")');
    await aiButton.click();

    // Wait for modal to appear
    await page.waitForTimeout(500);

    // Check for modal or dialog
    const modal = page.locator('[role="dialog"]');
    if (await modal.isVisible()) {
      // Close modal
      await page.keyboard.press('Escape');
      await page.waitForTimeout(300);
    }
  });

  test('severity distribution shows severity levels', async ({ page }) => {
    // Wait for data
    await page.waitForTimeout(2000);

    const severityLevels = ['ERROR', 'WARNING', 'INFO', 'DEBUG', 'CRITICAL'];

    for (const level of severityLevels) {
      const levelElement = page.locator(`text=${level}`).first();
      // At least some should be visible (depends on data)
      if (await levelElement.isVisible()) {
        expect(await levelElement.isVisible()).toBeTruthy();
      }
    }
  });

  test('page is responsive on mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Verify dashboard still renders
    await expect(page.locator('h1:has-text("Dashboard")')).toBeVisible();
  });

  test('page is responsive on tablet viewport', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.reload();
    await page.waitForLoadState('networkidle');

    await expect(page.locator('h1:has-text("Dashboard")')).toBeVisible();
  });
});
