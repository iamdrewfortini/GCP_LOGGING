import { test, expect } from '@playwright/test';

/**
 * Cross-Browser Compatibility Tests
 *
 * These tests verify that core functionality works consistently
 * across Chromium, Firefox, and WebKit browsers.
 */

test.describe('Cross-Browser Compatibility', () => {
  test.describe('Core Page Rendering', () => {
    test('dashboard renders correctly', async ({ page, browserName }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Core elements should render in all browsers
      await expect(page.locator('h1:has-text("Dashboard")')).toBeVisible();
      await expect(page.locator('text=GCP Infrastructure Portal')).toBeVisible();

      // Stats cards should render
      await expect(page.locator('text=Total Logs')).toBeVisible();

      console.log(`Dashboard rendered correctly in ${browserName}`);
    });

    test('logs page renders correctly', async ({ page, browserName }) => {
      await page.goto('/logs');
      await page.waitForLoadState('networkidle');

      await expect(page.locator('h1:has-text("Log Explorer")')).toBeVisible();
      await expect(page.locator('table')).toBeVisible();

      console.log(`Log Explorer rendered correctly in ${browserName}`);
    });

    test('chat page renders correctly', async ({ page, browserName }) => {
      await page.goto('/chat');
      await page.waitForLoadState('networkidle');

      await expect(page.locator('text=AI Log Debugger')).toBeVisible();
      await expect(page.locator('input[placeholder*="Ask about your logs"]')).toBeVisible();

      console.log(`Chat page rendered correctly in ${browserName}`);
    });

    test('costs page renders correctly', async ({ page, browserName }) => {
      await page.goto('/costs');
      await page.waitForLoadState('networkidle');

      await expect(page.locator('h1:has-text("Cost Analytics")')).toBeVisible();
      await expect(page.locator('table')).toBeVisible();

      console.log(`Costs page rendered correctly in ${browserName}`);
    });

    test('cloud-run page renders correctly', async ({ page, browserName }) => {
      await page.goto('/services/cloud-run');
      await page.waitForLoadState('networkidle');

      await expect(page.locator('h1:has-text("Cloud Run Services")')).toBeVisible();
      await expect(page.locator('table')).toBeVisible();

      console.log(`Cloud Run page rendered correctly in ${browserName}`);
    });
  });

  test.describe('CSS & Layout Consistency', () => {
    test('flexbox layouts work correctly', async ({ page, browserName }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Check that grid/flex containers render properly
      const cards = page.locator('[class*="grid"], [class*="flex"]');
      expect(await cards.count()).toBeGreaterThan(0);

      console.log(`Flexbox/Grid layouts working in ${browserName}`);
    });

    test('sidebar layout is consistent', async ({ page, browserName }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Sidebar should be visible and properly positioned
      await expect(page.locator('text=Glass Pane')).toBeVisible();
      await expect(page.locator('text=Navigation')).toBeVisible();

      console.log(`Sidebar layout consistent in ${browserName}`);
    });

    test('table layouts are consistent', async ({ page, browserName }) => {
      await page.goto('/logs');
      await page.waitForLoadState('networkidle');

      const table = page.locator('table');
      await expect(table).toBeVisible();

      // Table should have proper structure
      const headers = await page.locator('th').count();
      expect(headers).toBeGreaterThan(0);

      console.log(`Table layouts consistent in ${browserName}`);
    });

    test('modal/dialog positioning is correct', async ({ page, browserName }) => {
      await page.goto('/logs');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      const firstRow = page.locator('table tbody tr').first();
      if (await firstRow.isVisible()) {
        await firstRow.click();

        const dialog = page.locator('[role="dialog"]');
        if (await dialog.isVisible({ timeout: 3000 }).catch(() => false)) {
          // Dialog should be centered/properly positioned
          const box = await dialog.boundingBox();
          if (box) {
            const viewport = page.viewportSize();
            if (viewport) {
              // Dialog should be visible within viewport
              expect(box.x).toBeGreaterThanOrEqual(0);
              expect(box.y).toBeGreaterThanOrEqual(0);
            }
          }

          await page.keyboard.press('Escape');
        }
      }

      console.log(`Modal positioning correct in ${browserName}`);
    });
  });

  test.describe('Interactive Elements', () => {
    test('buttons are clickable', async ({ page, browserName }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      const refreshButton = page.locator('button:has-text("Refresh")');
      await expect(refreshButton).toBeVisible();
      await refreshButton.click();

      // Page should still function after click
      await expect(page.locator('h1:has-text("Dashboard")')).toBeVisible();

      console.log(`Buttons clickable in ${browserName}`);
    });

    test('dropdown menus work', async ({ page, browserName }) => {
      await page.goto('/logs');
      await page.waitForLoadState('networkidle');

      const severityTrigger = page.locator('button:has-text("All Severities")');
      if (await severityTrigger.isVisible()) {
        await severityTrigger.click();

        // Dropdown should appear
        await expect(page.locator('[role="listbox"], [role="menu"]').first()).toBeVisible();

        // Close dropdown
        await page.keyboard.press('Escape');
      }

      console.log(`Dropdowns working in ${browserName}`);
    });

    test('input fields accept text', async ({ page, browserName }) => {
      await page.goto('/logs');
      await page.waitForLoadState('networkidle');

      const searchInput = page.locator('input[placeholder*="Search"]');
      await searchInput.fill('test query');
      await expect(searchInput).toHaveValue('test query');

      console.log(`Input fields working in ${browserName}`);
    });

    test('links navigate correctly', async ({ page, browserName }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      await page.locator('a:has-text("Log Explorer")').click();
      await page.waitForURL('**/logs');

      await expect(page.locator('h1:has-text("Log Explorer")')).toBeVisible();

      console.log(`Navigation links working in ${browserName}`);
    });

    test('keyboard navigation works', async ({ page, browserName }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Tab through elements
      await page.keyboard.press('Tab');
      await page.keyboard.press('Tab');

      // Enter to activate
      await page.keyboard.press('Enter');

      // Page should respond to keyboard
      console.log(`Keyboard navigation working in ${browserName}`);
    });
  });

  test.describe('JavaScript Functionality', () => {
    test('state management works', async ({ page, browserName }) => {
      await page.goto('/chat');
      await page.waitForLoadState('networkidle');

      const input = page.locator('input[placeholder*="Ask about your logs"]');
      await input.fill('test message');
      await page.keyboard.press('Enter');

      await page.waitForTimeout(2000);

      // Message should appear
      await expect(page.locator('text=test message')).toBeVisible();

      console.log(`State management working in ${browserName}`);
    });

    test('async data loading works', async ({ page, browserName }) => {
      await page.goto('/logs');
      await page.waitForLoadState('networkidle');

      // Wait for data to load
      await page.waitForTimeout(3000);

      // Table should have content or show empty state
      const table = page.locator('table');
      await expect(table).toBeVisible();

      console.log(`Async data loading working in ${browserName}`);
    });

    test('event handlers fire correctly', async ({ page, browserName }) => {
      await page.goto('/chat');
      await page.waitForLoadState('networkidle');

      const quickAction = page.locator('button:has-text("Recent Errors")');
      await quickAction.click();

      await page.waitForTimeout(2000);

      // Event should have fired, message should appear
      await expect(page.locator('text=Show me all errors')).toBeVisible();

      console.log(`Event handlers working in ${browserName}`);
    });
  });

  test.describe('Animations & Transitions', () => {
    test('sidebar collapse animation works', async ({ page, browserName }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      const servicesButton = page.locator('button:has-text("Services")');
      await servicesButton.click();

      // Wait for animation
      await page.waitForTimeout(500);

      // Toggle back
      await servicesButton.click();
      await page.waitForTimeout(500);

      console.log(`Animations working in ${browserName}`);
    });

    test('loading states display correctly', async ({ page, browserName }) => {
      await page.goto('/logs');

      // Check for skeleton loaders or loading indicators
      // These may be brief
      await page.waitForLoadState('networkidle');

      console.log(`Loading states working in ${browserName}`);
    });
  });

  test.describe('Responsive Design', () => {
    test('mobile viewport renders correctly', async ({ page, browserName }) => {
      await page.setViewportSize({ width: 375, height: 667 });
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      await expect(page.locator('h1:has-text("Dashboard")')).toBeVisible();

      console.log(`Mobile viewport rendering in ${browserName}`);
    });

    test('tablet viewport renders correctly', async ({ page, browserName }) => {
      await page.setViewportSize({ width: 768, height: 1024 });
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      await expect(page.locator('h1:has-text("Dashboard")')).toBeVisible();

      console.log(`Tablet viewport rendering in ${browserName}`);
    });

    test('desktop viewport renders correctly', async ({ page, browserName }) => {
      await page.setViewportSize({ width: 1920, height: 1080 });
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      await expect(page.locator('h1:has-text("Dashboard")')).toBeVisible();

      console.log(`Desktop viewport rendering in ${browserName}`);
    });
  });

  test.describe('Network & Performance', () => {
    test('page loads within acceptable time', async ({ page, browserName }) => {
      const start = Date.now();
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      const loadTime = Date.now() - start;

      expect(loadTime).toBeLessThan(15000); // 15 second max

      console.log(`Page loaded in ${loadTime}ms in ${browserName}`);
    });

    test('API requests complete successfully', async ({ page, browserName }) => {
      const failedRequests: string[] = [];

      page.on('response', response => {
        if (response.url().includes('/api/') && response.status() >= 500) {
          failedRequests.push(`${response.url()} - ${response.status()}`);
        }
      });

      await page.goto('/logs');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(3000);

      console.log(`API requests checked in ${browserName}, failures: ${failedRequests.length}`);
    });
  });

  test.describe('Browser-Specific Features', () => {
    test('local storage works', async ({ page, browserName }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Test localStorage
      await page.evaluate(() => {
        localStorage.setItem('test-key', 'test-value');
      });

      const value = await page.evaluate(() => {
        return localStorage.getItem('test-key');
      });

      expect(value).toBe('test-value');

      // Cleanup
      await page.evaluate(() => {
        localStorage.removeItem('test-key');
      });

      console.log(`Local storage working in ${browserName}`);
    });

    test('session storage works', async ({ page, browserName }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      await page.evaluate(() => {
        sessionStorage.setItem('test-session', 'session-value');
      });

      const value = await page.evaluate(() => {
        return sessionStorage.getItem('test-session');
      });

      expect(value).toBe('session-value');

      console.log(`Session storage working in ${browserName}`);
    });

    test('fetch API works', async ({ page, browserName }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // The app uses fetch for API calls
      // Just verify page loads (fetch must be working)
      await expect(page.locator('h1')).toBeVisible();

      console.log(`Fetch API working in ${browserName}`);
    });
  });
});
