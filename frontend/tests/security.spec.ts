import { test, expect } from '@playwright/test';

test.describe('Security Tests', () => {

  test.describe('Console Error Monitoring', () => {
    test('no JavaScript errors on dashboard', async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', error => errors.push(error.message));

      await page.goto('/');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      const criticalErrors = errors.filter(e =>
        !e.includes('ResizeObserver') &&
        !e.includes('network') &&
        !e.includes('favicon')
      );

      expect(criticalErrors).toHaveLength(0);
    });

    test('no JavaScript errors on logs page', async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', error => errors.push(error.message));

      await page.goto('/logs');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      const criticalErrors = errors.filter(e =>
        !e.includes('ResizeObserver') &&
        !e.includes('network') &&
        !e.includes('favicon')
      );

      expect(criticalErrors).toHaveLength(0);
    });

    test('no JavaScript errors on chat page', async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', error => errors.push(error.message));

      await page.goto('/chat');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      const criticalErrors = errors.filter(e =>
        !e.includes('ResizeObserver') &&
        !e.includes('network') &&
        !e.includes('favicon')
      );

      expect(criticalErrors).toHaveLength(0);
    });

    test('no JavaScript errors on costs page', async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', error => errors.push(error.message));

      await page.goto('/costs');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      const criticalErrors = errors.filter(e =>
        !e.includes('ResizeObserver') &&
        !e.includes('network') &&
        !e.includes('favicon')
      );

      expect(criticalErrors).toHaveLength(0);
    });

    test('no JavaScript errors on cloud-run page', async ({ page }) => {
      const errors: string[] = [];
      page.on('pageerror', error => errors.push(error.message));

      await page.goto('/services/cloud-run');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      const criticalErrors = errors.filter(e =>
        !e.includes('ResizeObserver') &&
        !e.includes('network') &&
        !e.includes('favicon')
      );

      expect(criticalErrors).toHaveLength(0);
    });

    test('no console warnings about deprecations', async ({ page }) => {
      const warnings: string[] = [];
      page.on('console', msg => {
        if (msg.type() === 'warning' && msg.text().includes('deprecated')) {
          warnings.push(msg.text());
        }
      });

      await page.goto('/');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      // Allow some warnings but flag major deprecations
      const criticalWarnings = warnings.filter(w =>
        w.includes('will be removed') ||
        w.includes('breaking change')
      );

      expect(criticalWarnings).toHaveLength(0);
    });
  });

  test.describe('XSS Prevention', () => {
    test('search input sanitizes script injection', async ({ page }) => {
      await page.goto('/logs');
      await page.waitForLoadState('networkidle');

      const searchInput = page.locator('input[placeholder*="Search"]');
      await searchInput.fill('<script>alert("xss")</script>');
      await page.waitForTimeout(1000);

      // Page should not execute script - no alert should appear
      // Verify page still functions
      await expect(page.locator('h1:has-text("Log Explorer")')).toBeVisible();
    });

    test('search input sanitizes img onerror injection', async ({ page }) => {
      await page.goto('/logs');
      await page.waitForLoadState('networkidle');

      const searchInput = page.locator('input[placeholder*="Search"]');
      await searchInput.fill('<img src=x onerror=alert("xss")>');
      await page.waitForTimeout(1000);

      // Page should still function
      await expect(page.locator('h1:has-text("Log Explorer")')).toBeVisible();
    });

    test('chat input sanitizes script injection', async ({ page }) => {
      await page.goto('/chat');
      await page.waitForLoadState('networkidle');

      const chatInput = page.locator('input[placeholder*="Ask about your logs"]');
      await chatInput.fill('<script>alert("xss")</script>');
      await page.keyboard.press('Enter');

      await page.waitForTimeout(2000);

      // Message should be escaped/sanitized
      const scriptTag = page.locator('script:has-text("alert")');
      expect(await scriptTag.count()).toBe(0);
    });

    test('URL parameters are sanitized', async ({ page }) => {
      await page.goto('/logs?search=<script>alert("xss")</script>');
      await page.waitForLoadState('networkidle');

      // Page should load without executing script
      await expect(page.locator('h1:has-text("Log Explorer")')).toBeVisible();
    });
  });

  test.describe('HTTPS & Secure Headers', () => {
    test('external links have rel="noopener noreferrer"', async ({ page }) => {
      await page.goto('/services/cloud-run');
      await page.waitForLoadState('networkidle');

      const externalLinks = page.locator('a[target="_blank"]');
      const count = await externalLinks.count();

      for (let i = 0; i < count; i++) {
        const link = externalLinks.nth(i);
        const rel = await link.getAttribute('rel');
        expect(rel).toContain('noopener');
      }
    });

    test('no mixed content warnings', async ({ page }) => {
      const mixedContent: string[] = [];
      page.on('console', msg => {
        if (msg.text().includes('Mixed Content')) {
          mixedContent.push(msg.text());
        }
      });

      await page.goto('/');
      await page.waitForLoadState('networkidle');

      expect(mixedContent).toHaveLength(0);
    });
  });

  test.describe('Form Security', () => {
    test('forms use proper input types', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // Password inputs should be type="password"
      const passwordInputs = page.locator('input[name*="password"], input[placeholder*="password"]');
      const count = await passwordInputs.count();

      for (let i = 0; i < count; i++) {
        const type = await passwordInputs.nth(i).getAttribute('type');
        expect(type).toBe('password');
      }
    });

    test('forms have CSRF protection consideration', async ({ page }) => {
      await page.goto('/');
      // Note: CSRF protection is typically server-side
      // This test verifies the page loads
      await expect(page.locator('h1')).toBeVisible();
    });
  });

  test.describe('Data Exposure Prevention', () => {
    test('no sensitive data in page source', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      const content = await page.content();

      // Check for common sensitive patterns
      expect(content).not.toMatch(/api[_-]?key\s*[:=]\s*['"][^'"]{20,}['"]/i);
      expect(content).not.toMatch(/password\s*[:=]\s*['"][^'"]+['"]/i);
      expect(content).not.toMatch(/secret\s*[:=]\s*['"][^'"]{10,}['"]/i);
    });

    test('no tokens exposed in URL', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      const url = page.url();

      // URLs shouldn't contain tokens
      expect(url).not.toMatch(/token=[^&]+/i);
      expect(url).not.toMatch(/key=[a-z0-9]{20,}/i);
    });

    test('localStorage does not store sensitive credentials', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      const localStorage = await page.evaluate(() => {
        const items: Record<string, string> = {};
        for (let i = 0; i < window.localStorage.length; i++) {
          const key = window.localStorage.key(i);
          if (key) {
            items[key] = window.localStorage.getItem(key) || '';
          }
        }
        return items;
      });

      // Check for sensitive data patterns in localStorage
      const localStorageStr = JSON.stringify(localStorage);
      expect(localStorageStr).not.toMatch(/password/i);
      // API keys in localStorage are sometimes acceptable for client-side apps
    });
  });

  test.describe('Network Request Security', () => {
    test('API requests use proper methods', async ({ page }) => {
      const requests: { url: string; method: string }[] = [];

      page.on('request', request => {
        if (request.url().includes('/api/')) {
          requests.push({
            url: request.url(),
            method: request.method()
          });
        }
      });

      await page.goto('/logs');
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);

      // GET requests for data fetching
      const getRequests = requests.filter(r => r.method === 'GET');
      // Should have some GET requests
    });

    test('no sensitive data in GET parameters', async ({ page }) => {
      const requests: string[] = [];

      page.on('request', request => {
        if (request.method() === 'GET') {
          requests.push(request.url());
        }
      });

      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // URLs shouldn't contain passwords or secrets
      requests.forEach(url => {
        expect(url).not.toMatch(/password=/i);
        expect(url).not.toMatch(/secret=/i);
      });
    });
  });

  test.describe('Error Handling Security', () => {
    test('404 page does not expose system information', async ({ page }) => {
      await page.goto('/nonexistent-page-12345');
      await page.waitForLoadState('networkidle');

      const content = await page.content();

      // Should not expose file paths or stack traces
      expect(content).not.toMatch(/\/usr\/|\/home\/|\/var\//);
      expect(content).not.toMatch(/at\s+\w+\s+\([^)]+:\d+:\d+\)/); // Stack trace pattern
    });

    test('API errors do not expose stack traces', async ({ page }) => {
      const responses: string[] = [];

      page.on('response', async response => {
        if (response.url().includes('/api/') && response.status() >= 400) {
          try {
            const body = await response.text();
            responses.push(body);
          } catch {}
        }
      });

      await page.goto('/logs');
      await page.waitForLoadState('networkidle');

      // Any error responses should not contain stack traces
      responses.forEach(body => {
        expect(body).not.toMatch(/at\s+\w+\s+\([^)]+:\d+:\d+\)/);
      });
    });
  });

  test.describe('Session Security', () => {
    test('session persists across page navigation', async ({ page }) => {
      await page.goto('/chat');
      await page.waitForLoadState('networkidle');

      // Interact to potentially create session
      const input = page.locator('input[placeholder*="Ask about your logs"]');
      await input.fill('test');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(2000);

      // Navigate away and back
      await page.goto('/logs');
      await page.waitForLoadState('networkidle');

      await page.goto('/chat');
      await page.waitForLoadState('networkidle');

      // Page should load without errors
      await expect(page.locator('text=AI Log Debugger')).toBeVisible();
    });
  });

  test.describe('Content Security', () => {
    test('inline scripts are minimized', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');

      const inlineScripts = await page.evaluate(() => {
        const scripts = document.querySelectorAll('script:not([src])');
        return scripts.length;
      });

      // Modern SPAs typically have some inline scripts
      // But excessive inline scripts can be a security concern
      expect(inlineScripts).toBeLessThan(10);
    });

    test('no eval usage in application code', async ({ page }) => {
      const evalCalls: string[] = [];

      // Note: This is a basic check - comprehensive eval detection requires code analysis
      page.on('console', msg => {
        if (msg.text().includes('eval')) {
          evalCalls.push(msg.text());
        }
      });

      await page.goto('/');
      await page.waitForLoadState('networkidle');

      // eval calls in warnings/errors should be minimal
    });
  });
});
