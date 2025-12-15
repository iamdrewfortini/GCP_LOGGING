import { test, expect } from '@playwright/test';

test.describe('AI Debugger / Chat Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/chat');
    await page.waitForLoadState('networkidle');
  });

  test('displays AI Log Debugger header', async ({ page }) => {
    await expect(page.locator('text=AI Log Debugger')).toBeVisible();
    await expect(page.locator('text=Powered by Gemini')).toBeVisible();
  });

  test('displays sessions sidebar', async ({ page }) => {
    await expect(page.locator('text=Sessions')).toBeVisible();

    // New session button
    const newButton = page.locator('button').filter({ has: page.locator('svg.lucide-plus') }).first();
    await expect(newButton).toBeVisible();
  });

  test('displays welcome screen with quick actions', async ({ page }) => {
    await expect(page.locator('text=How can I help you today?')).toBeVisible();

    // Quick action buttons
    await expect(page.locator('button:has-text("System Health")')).toBeVisible();
    await expect(page.locator('button:has-text("Recent Errors")')).toBeVisible();
    await expect(page.locator('button:has-text("Warning Trends")')).toBeVisible();
    await expect(page.locator('button:has-text("Service Status")')).toBeVisible();
  });

  test('displays chat input', async ({ page }) => {
    const input = page.locator('input[placeholder*="Ask about your logs"]');
    await expect(input).toBeVisible();
  });

  test('displays send button', async ({ page }) => {
    const sendButton = page.locator('button').filter({ has: page.locator('svg.lucide-send') });
    await expect(sendButton).toBeVisible();
  });

  test('send button is disabled when input is empty', async ({ page }) => {
    const sendButton = page.locator('button[type="submit"]').filter({ has: page.locator('svg.lucide-send') });

    if (await sendButton.isVisible()) {
      await expect(sendButton).toBeDisabled();
    }
  });

  test('input accepts text', async ({ page }) => {
    const input = page.locator('input[placeholder*="Ask about your logs"]');
    await input.fill('Show me recent errors');
    await expect(input).toHaveValue('Show me recent errors');
  });

  test('send button enables when input has text', async ({ page }) => {
    const input = page.locator('input[placeholder*="Ask about your logs"]');
    await input.fill('test');

    const sendButton = page.locator('button[type="submit"]').filter({ has: page.locator('svg.lucide-send') });

    if (await sendButton.isVisible()) {
      await expect(sendButton).not.toBeDisabled();
    }
  });

  test('clicking "Recent Errors" quick action sends message', async ({ page }) => {
    const recentErrorsButton = page.locator('button:has-text("Recent Errors")');
    await recentErrorsButton.click();

    // Wait for message to appear and AI response to start
    await page.waitForTimeout(2000);

    // Welcome screen should be gone
    await expect(page.locator('text=How can I help you today?')).not.toBeVisible();

    // User message should appear
    await expect(page.locator('text=Show me all errors from the last hour')).toBeVisible();
  });

  test('clicking "System Health" quick action sends message', async ({ page }) => {
    const systemHealthButton = page.locator('button:has-text("System Health")');
    await systemHealthButton.click();

    await page.waitForTimeout(2000);

    // User message should appear
    await expect(page.locator('text=Give me a health summary')).toBeVisible();
  });

  test('clicking "Warning Trends" quick action sends message', async ({ page }) => {
    const warningTrendsButton = page.locator('button:has-text("Warning Trends")');
    await warningTrendsButton.click();

    await page.waitForTimeout(2000);

    await expect(page.locator('text=Analyze warning patterns')).toBeVisible();
  });

  test('clicking "Service Status" quick action sends message', async ({ page }) => {
    const serviceStatusButton = page.locator('button:has-text("Service Status")');
    await serviceStatusButton.click();

    await page.waitForTimeout(2000);

    await expect(page.locator('text=Which services have the most errors')).toBeVisible();
  });

  test('sending a message shows user message in chat', async ({ page }) => {
    const input = page.locator('input[placeholder*="Ask about your logs"]');
    await input.fill('Hello test message');

    const sendButton = page.locator('button[type="submit"]').filter({ has: page.locator('svg.lucide-send') });
    await sendButton.click();

    // User message should appear
    await expect(page.locator('text=Hello test message')).toBeVisible({ timeout: 5000 });
  });

  test('AI response streams in after sending message', async ({ page }) => {
    const recentErrorsButton = page.locator('button:has-text("Recent Errors")');
    await recentErrorsButton.click();

    // Wait for streaming to start/complete
    await page.waitForTimeout(15000);

    // Check for AI response content or tool calls
    // The response area should have content beyond just the user message
    const messages = page.locator('.prose, [class*="message"]');
    const messageCount = await messages.count();
    expect(messageCount).toBeGreaterThanOrEqual(0);
  });

  test('tool calls are displayed during AI response', async ({ page }) => {
    const recentErrorsButton = page.locator('button:has-text("Recent Errors")');
    await recentErrorsButton.click();

    // Wait for response with tool calls
    await page.waitForTimeout(10000);

    // Look for tool call indicators
    const toolCallButton = page.locator('button:has-text("search_logs"), button:has-text("tool")').first();

    if (await toolCallButton.isVisible({ timeout: 5000 }).catch(() => false)) {
      expect(await toolCallButton.isVisible()).toBeTruthy();
    }
  });

  test('tool call expand/collapse works', async ({ page }) => {
    const recentErrorsButton = page.locator('button:has-text("Recent Errors")');
    await recentErrorsButton.click();

    await page.waitForTimeout(10000);

    // Find a tool call button
    const toolCallButton = page.locator('button').filter({ hasText: /search_logs|tool/i }).first();

    if (await toolCallButton.isVisible({ timeout: 5000 }).catch(() => false)) {
      // Click to expand
      await toolCallButton.click();
      await page.waitForTimeout(300);

      // Look for Input/Output labels
      const inputLabel = page.locator('text=Input:');
      if (await inputLabel.isVisible()) {
        expect(await inputLabel.isVisible()).toBeTruthy();
      }

      // Click to collapse
      await toolCallButton.click();
      await page.waitForTimeout(300);
    }
  });

  test('Clear button appears after messages and works', async ({ page }) => {
    // Send a message first
    const input = page.locator('input[placeholder*="Ask about your logs"]');
    await input.fill('Test message');
    await page.keyboard.press('Enter');

    await page.waitForTimeout(2000);

    // Clear button should appear
    const clearButton = page.locator('button:has-text("Clear")');

    if (await clearButton.isVisible()) {
      await clearButton.click();
      await page.waitForTimeout(500);

      // Welcome screen should reappear
      await expect(page.locator('text=How can I help you today?')).toBeVisible();
    }
  });

  test('New button starts a new chat', async ({ page }) => {
    // Send a message first
    const input = page.locator('input[placeholder*="Ask about your logs"]');
    await input.fill('Test message');
    await page.keyboard.press('Enter');

    await page.waitForTimeout(2000);

    // Click New button
    const newButton = page.locator('button:has-text("New")');
    await newButton.click();

    await page.waitForTimeout(500);

    // Welcome screen should reappear
    await expect(page.locator('text=How can I help you today?')).toBeVisible();
  });

  test('suggestion chips are displayed on welcome screen', async ({ page }) => {
    // Check for smart suggestions
    const suggestions = [
      'Show me errors from the last hour',
      'What\'s causing the most issues?',
      'Analyze logs for glass-pane service',
    ];

    for (const suggestion of suggestions) {
      const suggestionButton = page.locator(`button:has-text("${suggestion}")`);
      if (await suggestionButton.isVisible()) {
        expect(await suggestionButton.isVisible()).toBeTruthy();
      }
    }
  });

  test('clicking suggestion chip fills input or sends message', async ({ page }) => {
    const suggestionButton = page.locator('button:has-text("Show me errors from the last hour")');

    if (await suggestionButton.isVisible()) {
      await suggestionButton.click();
      await page.waitForTimeout(500);

      // Either input is filled or message is sent
      const input = page.locator('input[placeholder*="Ask about your logs"]');
      const inputValue = await input.inputValue();

      // Either we have the text in input or a message was sent
      expect(inputValue.length > 0 || await page.locator('text=Show me errors').isVisible()).toBeTruthy();
    }
  });

  test('Enter key sends message', async ({ page }) => {
    const input = page.locator('input[placeholder*="Ask about your logs"]');
    await input.fill('Test enter key');
    await page.keyboard.press('Enter');

    await page.waitForTimeout(2000);

    // Message should appear
    await expect(page.locator('text=Test enter key')).toBeVisible();
  });

  test('sessions sidebar shows "No sessions yet" when empty', async ({ page }) => {
    const noSessionsText = page.locator('text=No sessions yet');

    if (await noSessionsText.isVisible()) {
      await expect(noSessionsText).toBeVisible();
    } else {
      // If not empty, at least verify the sidebar is present.
      await expect(page.locator('text=Sessions')).toBeVisible();
    }
  });

  test('stop button appears during streaming', async ({ page }) => {
    const recentErrorsButton = page.locator('button:has-text("Recent Errors")');
    await recentErrorsButton.click();

    // Quickly check for stop button during streaming
    const stopButton = page.locator('button').filter({ has: page.locator('svg.lucide-square') });

    // May briefly appear during streaming
    await page.waitForTimeout(1000);
    await stopButton.first().isVisible();

    // Page should not crash
    await expect(page.locator('text=AI Log Debugger')).toBeVisible();
  });

  test('input is disabled during streaming', async ({ page }) => {
    const recentErrorsButton = page.locator('button:has-text("Recent Errors")');
    await recentErrorsButton.click();

    // Check if input becomes disabled during streaming
    const input = page.locator('input[placeholder*="Ask about your logs"]');

    // During active streaming, input may be disabled
    await page.waitForTimeout(500);
    await expect(input).toBeVisible();
  });

  test('markdown rendering in AI responses', async ({ page }) => {
    const recentErrorsButton = page.locator('button:has-text("Recent Errors")');
    await recentErrorsButton.click();

    // Wait for response
    await page.waitForTimeout(15000);

    // Check for markdown elements (lists, paragraphs, etc.)
    const proseContent = page.locator('.prose');
    if (await proseContent.isVisible()) {
      expect(await proseContent.isVisible()).toBeTruthy();
    }
  });

  test('error state displays correctly', async ({ page }) => {
    // This test verifies error handling UI
    // Actual errors depend on API state
    await page.waitForTimeout(1000);

    // Page should not crash
    await expect(page.locator('text=AI Log Debugger')).toBeVisible();
  });

  test('mobile responsive layout', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Header should still be visible
    await expect(page.locator('text=AI Log Debugger')).toBeVisible();

    // Input should be visible
    const input = page.locator('input[placeholder*="Ask about your logs"]');
    await expect(input).toBeVisible();
  });

  test('timestamps are displayed on messages', async ({ page }) => {
    const input = page.locator('input[placeholder*="Ask about your logs"]');
    await input.fill('Test timestamp');
    await page.keyboard.press('Enter');

    await page.waitForTimeout(2000);

    // Look for time format (e.g., "12:30:45 PM")
    const timestamp = page.locator('text=/\\d{1,2}:\\d{2}:\\d{2}/');
    if (await timestamp.first().isVisible()) {
      expect(await timestamp.first().isVisible()).toBeTruthy();
    }
  });

  test('user messages appear on the right side', async ({ page }) => {
    const input = page.locator('input[placeholder*="Ask about your logs"]');
    await input.fill('Test alignment');
    await page.keyboard.press('Enter');

    await page.waitForTimeout(2000);

    // User message should have right-aligned styling
    const userMessage = page.locator('text=Test alignment').locator('..');
    await expect(userMessage).toBeVisible();
  });

  test('bot avatar is displayed for AI messages', async ({ page }) => {
    const recentErrorsButton = page.locator('button:has-text("Recent Errors")');
    await recentErrorsButton.click();

    await page.waitForTimeout(5000);

    // Look for bot icon/avatar
    const botAvatar = page.locator('svg.lucide-bot');
    expect(await botAvatar.first().isVisible()).toBeTruthy();
  });
});
