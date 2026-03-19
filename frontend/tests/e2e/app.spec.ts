import { test, expect } from '@playwright/test';

const mockCases = [
  {
    id: 'case-12345678-abcdef',
    query: 'Mock case',
    conflictDomain: 'test-domain',
    status: 'review ready',
    stage: 'REVIEW',
    counts: { articles: 5, events: 2, reviewItems: 1 },
    reportPath: null,
    automationMode: 'safe',
    hasNewMaterial: true,
    openExceptionsCount: 1,
    lastUpdated: '2026-03-19T00:00:00Z',
  },
];

test.describe('App Smoke Tests', () => {
  test('should load the dashboard', async ({ page }) => {
    await page.goto('/dashboard');
    await expect(page).toHaveTitle(/Triangulate/i);
  });

  test('should navigate to cases page', async ({ page }) => {
    await page.goto('/cases');
    await expect(page.locator('text=Cases')).toBeVisible();
  });

  test('should open case detail from dashboard lists', async ({ page }) => {
    await page.route('**/api/cases', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockCases),
      });
    });

    await page.route('**/api/cases/case-12345678-abcdef', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          case: mockCases[0],
        }),
      });
    });

    await page.goto('/dashboard');
    await page.getByText('Mock case').first().click();
    await expect(page).toHaveURL(/\/cases\/case-12345678-abcdef$/);
    await expect(page.getByRole('heading', { name: 'Mock case' })).toBeVisible();
  });
});
