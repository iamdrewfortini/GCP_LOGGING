import { test, expect } from '@playwright/test';

test.describe('Logging UI Smoke Tests', () => {
  test('Log Explorer (/logs) loads and functions correctly', async ({ page }) => {
    // Set up console error tracking BEFORE any navigation
    const consoleErrors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    // Navigate to /logs
    await page.goto('/logs');

    // Wait for page to stabilize
    await page.waitForLoadState('networkidle');

    // Assert page loads with logs table
    await expect(page.locator('table')).toBeVisible({ timeout: 10000 });

    // Test Stream toggle (if present)
    const streamButton = page.locator('button:has-text("Stream")');
    if (await streamButton.isVisible()) {
      await streamButton.click();
      await expect(page.locator('button:has-text("Stop")')).toBeVisible();
      await page.locator('button:has-text("Stop")').click();
      await expect(streamButton).toBeVisible();
    }

    // Test row click opens Log Details modal (if rows exist)
    const firstRow = page.locator('table tbody tr').first();
    if (await firstRow.isVisible()) {
      await firstRow.click();
      const modal = page.locator('[role="dialog"]');
      await expect(modal).toBeVisible({ timeout: 5000 });
      // Verify fields in modal - use label selector to avoid matching content
      await expect(modal.getByText('Severity', { exact: true }).first()).toBeVisible();
      await expect(modal.getByText('Service', { exact: true }).first()).toBeVisible();
      // Close modal
      const closeButton = modal.locator('button:has-text("Close")');
      if (await closeButton.isVisible()) {
        await closeButton.click();
      } else {
        // Try clicking outside or pressing Escape
        await page.keyboard.press('Escape');
      }
      await expect(modal).not.toBeVisible();
    }

    // Test search box (if present)
    const searchBox = page.locator('input[placeholder*="search" i]');
    if (await searchBox.isVisible()) {
      // Type a search term
      await searchBox.fill('error');
      // Wait for filtering/API call to complete
      await page.waitForTimeout(1000);
      // Verify search input has the value
      await expect(searchBox).toHaveValue('error');
      // Verify the table still renders (search was processed without breaking UI)
      await expect(page.locator('table')).toBeVisible();
      // Clear search
      await searchBox.clear();
      await page.waitForTimeout(500);
    }

    // Verify no console errors occurred
    expect(consoleErrors.filter(e => !e.includes('favicon'))).toHaveLength(0);
  });

  test('AI Debugger (/chat) quick actions work', async ({ page }) => {
    // Set up console error tracking
    const consoleErrors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    await page.goto('/chat');
    await page.waitForLoadState('networkidle');

    // Assert quick actions render
    await expect(page.locator('text=System Health')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=Recent Errors')).toBeVisible();
    await expect(page.locator('text=Warning Trends')).toBeVisible();
    await expect(page.locator('text=Service Status')).toBeVisible();

    // Test "Recent Errors" quick action
    const recentErrorsButton = page.locator('button:has-text("Recent Errors")');
    await recentErrorsButton.click();

    // Wait for AI response to appear (look for message container or streaming indicator)
    // The response should contain tool calls and markdown content
    await page.waitForSelector('[data-testid="assistant-message"], .assistant-message, [class*="message"]', {
      timeout: 30000, // AI responses can take time
    }).catch(() => {
      // If no specific selector, wait for any new content
    });

    // Wait for streaming to complete (no loading indicator)
    await page.waitForTimeout(2000);

    // Assert response has markdown content (lists, paragraphs, etc.)
    const responseArea = page.locator('main, [role="main"], .chat-container').first();
    await expect(responseArea.locator('ul, ol, p').first()).toBeVisible({ timeout: 30000 });

    // Assert tool calls shown (if visible)
    const toolCallIndicator = page.locator('text=search_logs_tool, text=tool, text=Tool');
    if (await toolCallIndicator.first().isVisible({ timeout: 5000 }).catch(() => false)) {
      // Test expand/collapse if tool call UI exists
      const expandButton = page.locator('button:has-text("Input"), button:has-text("Show"), [data-testid="expand-tool"]').first();
      if (await expandButton.isVisible()) {
        await expandButton.click();
        await page.waitForTimeout(300);
        await expandButton.click();
      }
    }

    // Verify no critical console errors (ignore expected warnings)
    const criticalErrors = consoleErrors.filter(e =>
      !e.includes('favicon') &&
      !e.includes('DevTools') &&
      !e.includes('React') // Ignore React dev warnings
    );
    expect(criticalErrors).toHaveLength(0);
  });
});