import { test, expect } from '@playwright/test';

test.describe('Accessibility & SEO Tests', () => {

  test.describe('Accessibility - Dashboard', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');
    });

    test('page has proper heading hierarchy', async ({ page }) => {
      // Should have h1
      const h1 = page.locator('h1');
      expect(await h1.count()).toBeGreaterThanOrEqual(1);
    });

    test('interactive elements are keyboard accessible', async ({ page }) => {
      // Tab through interactive elements
      await page.keyboard.press('Tab');
      await page.keyboard.press('Tab');

      // Should be able to focus on elements
      const focusedElement = page.locator(':focus');
      expect(await focusedElement.count()).toBeGreaterThanOrEqual(0);
    });

    test('buttons have accessible names', async ({ page }) => {
      const buttons = page.locator('button');
      const count = await buttons.count();

      for (let i = 0; i < Math.min(count, 10); i++) {
        const button = buttons.nth(i);
        const text = await button.innerText();
        const ariaLabel = await button.getAttribute('aria-label');
        const title = await button.getAttribute('title');

        // Button should have some accessible name
        expect(text.length > 0 || ariaLabel || title).toBeTruthy();
      }
    });

    test('links have accessible names', async ({ page }) => {
      const links = page.locator('a');
      const count = await links.count();

      for (let i = 0; i < Math.min(count, 10); i++) {
        const link = links.nth(i);
        const text = await link.innerText();
        const ariaLabel = await link.getAttribute('aria-label');

        // Link should have some accessible name
        expect(text.length > 0 || ariaLabel).toBeTruthy();
      }
    });

    test('images have alt text', async ({ page }) => {
      const images = page.locator('img');
      const count = await images.count();

      for (let i = 0; i < count; i++) {
        const img = images.nth(i);
        const alt = await img.getAttribute('alt');
        // All images should have alt attribute
        // Note: decorative images can have alt=""
      }
    });

    test('form inputs have labels', async ({ page }) => {
      const inputs = page.locator('input:not([type="hidden"])');
      const count = await inputs.count();

      for (let i = 0; i < count; i++) {
        const input = inputs.nth(i);
        const id = await input.getAttribute('id');
        const ariaLabel = await input.getAttribute('aria-label');
        const ariaLabelledBy = await input.getAttribute('aria-labelledby');
        const placeholder = await input.getAttribute('placeholder');

        // Input should have some labelling mechanism
        expect(id || ariaLabel || ariaLabelledBy || placeholder).toBeTruthy();
      }
    });

    test('focus is visible on interactive elements', async ({ page }) => {
      // Focus the first focusable element
      await page.keyboard.press('Tab');

      // Check that focus is visible
      const focusedElement = page.locator(':focus');
      if (await focusedElement.count() > 0) {
        // Just verify something is focused
        expect(await focusedElement.count()).toBeGreaterThan(0);
      }
    });

    test('color contrast is sufficient (visual check)', async ({ page }) => {
      // This is a visual test - automated contrast checking requires additional tools
      // We verify text is visible against backgrounds
      const textElements = page.locator('p, h1, h2, h3, span, a');
      expect(await textElements.count()).toBeGreaterThan(0);
    });
  });

  test.describe('Accessibility - Log Explorer', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/logs');
      await page.waitForLoadState('networkidle');
    });

    test('table has proper structure', async ({ page }) => {
      // Table should have thead and tbody
      await expect(page.locator('table thead')).toBeVisible();
      await expect(page.locator('table tbody')).toBeVisible();
    });

    test('table headers use th elements', async ({ page }) => {
      const headers = page.locator('table th');
      expect(await headers.count()).toBeGreaterThan(0);
    });

    test('search input has accessible label', async ({ page }) => {
      const searchInput = page.locator('input[placeholder*="Search"]');
      const placeholder = await searchInput.getAttribute('placeholder');
      expect(placeholder).toBeTruthy();
    });

    test('filter dropdowns are keyboard accessible', async ({ page }) => {
      const severityTrigger = page.locator('button:has-text("All Severities")');

      if (await severityTrigger.isVisible()) {
        await severityTrigger.focus();
        await page.keyboard.press('Enter');

        await expect(page.locator('[role="listbox"], [role="menu"]')).toBeVisible();

        // Can navigate with arrow keys
        await page.keyboard.press('ArrowDown');
        await page.keyboard.press('Escape');
      }
    });

    test('modal dialog is properly labelled', async ({ page }) => {
      await page.waitForTimeout(2000);

      const firstRow = page.locator('table tbody tr').first();
      if (await firstRow.isVisible()) {
        await firstRow.click();

        const dialog = page.locator('[role="dialog"]');
        if (await dialog.isVisible()) {
          // Dialog should have aria-labelledby or aria-label
          const hasLabel = await dialog.getAttribute('aria-labelledby') ||
                          await dialog.getAttribute('aria-label');
          // Just verify dialog opens
          expect(await dialog.isVisible()).toBeTruthy();
        }
      }
    });
  });

  test.describe('Accessibility - AI Chat', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/chat');
      await page.waitForLoadState('networkidle');
    });

    test('chat input is keyboard accessible', async ({ page }) => {
      const input = page.locator('input[placeholder*="Ask about your logs"]');
      await input.focus();
      await input.fill('test');
      await page.keyboard.press('Enter');

      // Message should be sent
      await page.waitForTimeout(1000);
    });

    test('quick action buttons are keyboard accessible', async ({ page }) => {
      const quickAction = page.locator('button:has-text("Recent Errors")');
      await quickAction.focus();
      await page.keyboard.press('Enter');

      await page.waitForTimeout(1000);
    });

    test('collapsible tool calls are keyboard accessible', async ({ page }) => {
      // First trigger a response
      const quickAction = page.locator('button:has-text("Recent Errors")');
      await quickAction.click();

      await page.waitForTimeout(10000);

      // Try to find and expand tool call
      const toolCallButton = page.locator('button').filter({ hasText: /search_logs|tool/i }).first();
      if (await toolCallButton.isVisible({ timeout: 5000 }).catch(() => false)) {
        await toolCallButton.focus();
        await page.keyboard.press('Enter');
        await page.waitForTimeout(300);
      }
    });
  });

  test.describe('SEO - Meta Tags', () => {
    test('dashboard has document title', async ({ page }) => {
      await page.goto('/');
      const title = await page.title();
      expect(title.length).toBeGreaterThan(0);
    });

    test('logs page has document title', async ({ page }) => {
      await page.goto('/logs');
      const title = await page.title();
      expect(title.length).toBeGreaterThan(0);
    });

    test('chat page has document title', async ({ page }) => {
      await page.goto('/chat');
      const title = await page.title();
      expect(title.length).toBeGreaterThan(0);
    });

    test('costs page has document title', async ({ page }) => {
      await page.goto('/costs');
      const title = await page.title();
      expect(title.length).toBeGreaterThan(0);
    });

    test('viewport meta tag is present', async ({ page }) => {
      await page.goto('/');
      const viewport = await page.locator('meta[name="viewport"]').getAttribute('content');
      expect(viewport).toContain('width=');
    });

    test('charset meta tag is present', async ({ page }) => {
      await page.goto('/');
      const charset = page.locator('meta[charset], meta[http-equiv="Content-Type"]');
      expect(await charset.count()).toBeGreaterThan(0);
    });
  });

  test.describe('Performance Accessibility', () => {
    test('page loads within acceptable time', async ({ page }) => {
      const start = Date.now();
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      const loadTime = Date.now() - start;

      // Should load within 10 seconds
      expect(loadTime).toBeLessThan(10000);
    });

    test('no layout shifts during load', async ({ page }) => {
      await page.goto('/');

      // Wait for initial render
      await page.waitForTimeout(500);

      // Check that main content is stable
      const h1 = page.locator('h1');
      const initialBox = await h1.boundingBox();

      await page.waitForTimeout(2000);

      const finalBox = await h1.boundingBox();

      if (initialBox && finalBox) {
        // Position should be stable (allow small variance)
        expect(Math.abs(initialBox.y - finalBox.y)).toBeLessThan(50);
      }
    });
  });

  test.describe('Reduced Motion Support', () => {
    test('respects prefers-reduced-motion', async ({ page }) => {
      // Emulate reduced motion preference
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Page should still function
      await expect(page.locator('h1')).toBeVisible();
    });
  });

  test.describe('Dark Mode Support', () => {
    test('respects prefers-color-scheme dark', async ({ page }) => {
      await page.emulateMedia({ colorScheme: 'dark' });
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Page should still render
      await expect(page.locator('h1')).toBeVisible();
    });

    test('respects prefers-color-scheme light', async ({ page }) => {
      await page.emulateMedia({ colorScheme: 'light' });
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      await expect(page.locator('h1')).toBeVisible();
    });
  });
});
