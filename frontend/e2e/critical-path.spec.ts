import { expect, test } from '@playwright/test'
import path from 'node:path'

test('uploads, annotates, persists, and exports a project', async ({ page }) => {
  await page.goto('/catalogs/new')
  await page.getByLabel('Catalog name').fill('E2E targets')
  await page.getByLabel('Catalog ZIP').setInputFiles(path.resolve('../sample_data/sample_reference_catalog.zip'))
  await page.getByRole('button', { name: 'Upload catalog' }).click()
  await expect(page.getByRole('heading', { name: 'E2E targets' })).toBeVisible()

  await page.goto('/projects/new')
  await page.getByLabel('Project name').fill('E2E dataset')
  await page.getByLabel('Reference catalog').selectOption({ label: 'E2E targets' })
  await page.getByLabel('Dataset ZIP').setInputFiles(path.resolve('../sample_data/sample_dataset.zip'))
  await page.getByRole('button', { name: 'Create project' }).click()
  await expect(page.getByRole('heading', { name: 'E2E dataset' })).toBeVisible()

  for (let index = 0; index < 20 && await page.getByRole('button', { name: 'Object 1' }).count() === 0; index += 1) {
    const next = page.getByRole('button', { name: 'Next Image' })
    if (await next.isDisabled()) break
    await next.click()
  }
  await page.getByRole('button', { name: 'Object 1' }).click()
  await page.getByRole('button', { name: /class 17$/i }).click()
  await expect(page.getByLabel('Current target 17')).toBeVisible()

  await page.goto('/catalogs')
  await page.getByRole('link', { name: /E2E dataset/i }).click()
  await expect(page.getByLabel('Current target 17')).toBeVisible()
  const download = page.waitForEvent('download')
  await page.getByRole('link', { name: 'Export labels' }).click()
  expect((await download).suggestedFilename()).toMatch(/corrected_labels\.zip$/)
})
