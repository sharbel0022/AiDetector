"""Focused TextLab v3 interaction regressions; external model responses are controlled fixtures."""
import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright, expect

ORIGINAL = 'Åsa leder Projekt Atlas. Vi betalade 125 kr.'
REWRITTEN = 'Åsa ansvarar för Projekt Atlas. Vi betalade 125 kr.'

async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 1050})
        failures = []
        page.on('pageerror', lambda error: failures.append(str(error)))
        await page.route('**/api/health', lambda route: route.fulfill(json={'provider':'ollama','model':'test-model','auth_required':False,'version':'3.0.0'}))
        await page.route('**/api/provider-status', lambda route: route.fulfill(json={'ready':False,'verified':False,'message':'Test: modellanslutningen är inte verifierad.'}))
        await page.goto(os.getenv('TEXTLAB_TEST_URL', 'http://127.0.0.1:8767'), wait_until='networkidle')
        await page.get_by_role('button', name='AI-humanizer').click()
        editor = page.get_by_role('textbox', name='Din originaltext', exact=True)
        await editor.fill(ORIGINAL)
        for tone in ['Naturlig', 'Enklare', 'Professionell', 'Akademisk', 'Kortare', 'Utförligare']:
            await expect(page.get_by_role('radio', name=tone, exact=True)).to_be_attached()
        await page.get_by_role('radio',name='Akademisk',exact=True).check()
        await page.get_by_role('combobox',name='Textens språk').select_option('en')
        await page.locator('.protected-options summary').click()
        await page.get_by_label('Textdelar att behålla exakt').fill('Åsa\nProjekt Atlas')
        async def rewrite(route):
            payload = route.request.post_data_json
            assert payload['tone'] == 'academic' and payload['language'] == 'en'
            assert payload['protected_terms'] == ['Åsa','Projekt Atlas']
            await route.fulfill(json={'text':REWRITTEN,'diff':[{'kind':'delete','text':ORIGINAL},{'kind':'insert','text':REWRITTEN}],'protected_count':3,'review_required':True,'provider':'mock','model':'test-only','warning':'Kontrollera betydelsen.'})
        await page.route('**/api/rewrite', rewrite)
        await editor.press('Control+Enter')
        await expect(page.locator('.output')).to_have_text(REWRITTEN)
        await expect(editor).to_have_value(ORIGINAL)
        await page.context.grant_permissions(['clipboard-read','clipboard-write'])
        await page.get_by_role('button',name='Kopiera omskriven text').click()
        assert await page.evaluate('navigator.clipboard.readText()') == REWRITTEN
        await page.get_by_label('Visa ändringar').check()
        await expect(page.locator('.output ins')).to_have_text(REWRITTEN)
        await expect(page.locator('.output del')).to_have_text(ORIGINAL)
        async with page.expect_download() as download_info:
            await page.get_by_role('button',name='Ladda ner omskriven text').click()
        download = await download_info.value
        assert download.suggested_filename == 'textlab-omskriven.txt'
        assert Path(await download.path()).read_text(encoding='utf8') == REWRITTEN
        await page.get_by_role('button',name='Använd som original').click()
        await expect(editor).to_have_value(REWRITTEN)
        await expect(page.locator('.output')).to_have_count(0)
        await page.get_by_role('button',name='Återställ original',exact=True).click()
        await expect(editor).to_have_value(ORIGINAL)
        await page.unroute('**/api/rewrite')
        async def slow(route):
            await asyncio.sleep(.4)
            try:
                await route.fulfill(json={'text':REWRITTEN,'diff':[{'kind':'delete','text':ORIGINAL},{'kind':'insert','text':REWRITTEN}],'protected_count':3})
            except Exception:
                pass
        await page.route('**/api/rewrite', slow)
        await page.get_by_role('button',name='Skriv om med AI',exact=True).click()
        await page.get_by_role('button',name='Avbryt',exact=True).click()
        await page.wait_for_timeout(550)
        await expect(page.locator('.output')).to_have_count(0)
        await expect(editor).to_have_value(ORIGINAL)
        await expect(page.get_by_role('button',name='Skriv om med AI',exact=True)).to_be_enabled()
        await page.unroute('**/api/rewrite')
        await page.route('**/api/rewrite', lambda route: route.fulfill(json={'text':REWRITTEN,'diff':[{'kind':'equal','text':'unrelated'}],'protected_count':0}))
        await page.get_by_role('button',name='Skriv om med AI',exact=True).click()
        await expect(page.get_by_role('alert')).to_contain_text('jämförelse')
        await expect(page.locator('.output')).to_have_count(0)
        # A correct text/diff contract must still reject values that would crash React.
        for field in ['provider','model','warning']:
            await page.unroute('**/api/rewrite')
            malformed = {'text':REWRITTEN,'diff':[{'kind':'delete','text':ORIGINAL},{'kind':'insert','text':REWRITTEN}],'protected_count':3,field:{'invalid':'object'}}
            async def malformed_rewrite(route):
                await route.fulfill(json=malformed)
            await page.route('**/api/rewrite', malformed_rewrite)
            await page.get_by_role('button',name='Skriv om med AI',exact=True).click()
            await expect(page.get_by_role('alert')).to_contain_text('metadata')
            await expect(editor).to_have_value(ORIGINAL)
            await expect(page.locator('.output')).to_have_count(0)
        # Independently exercise each rendered health/status metadata field.
        for malformed_health, malformed_status in [
            ({'provider':{'bad':True},'model':'test'}, {'ready':False,'verified':False,'message':'Kontroll ej verifierad.'}),
            ({'provider':'ollama','model':{'bad':True}}, {'ready':False,'verified':False,'message':'Kontroll ej verifierad.'}),
            ({'provider':'ollama','model':'test'}, {'ready':False,'verified':False,'message':{'bad':True}}),
        ]:
            await page.unroute('**/api/health')
            await page.unroute('**/api/provider-status')
            async def bad_health(route):
                await route.fulfill(json=malformed_health)
            async def bad_status(route):
                await route.fulfill(json=malformed_status)
            await page.route('**/api/health', bad_health)
            await page.route('**/api/provider-status', bad_status)
            await page.get_by_role('button',name='Kontrollera igen',exact=True).click()
            await expect(page.locator('.empty [role="alert"]')).to_contain_text('Kontrollera backend')
            await expect(editor).to_have_value(ORIGINAL)
            await expect(page.get_by_role('button',name='Anslut AI-backend')).to_be_enabled()
        await page.get_by_role('button',name='Inställningar').click()
        await expect(page.get_by_role('dialog')).to_be_visible()
        await page.keyboard.press('Escape')
        await expect(page.get_by_role('button',name='Inställningar')).to_be_focused()
        await page.set_viewport_size({'width':320,'height':740})
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not failures, failures
        await browser.close()
        print('TextLab v3 UI: six modes, language, protected terms, keyboard submit, diff, TXT export, apply/restore, cancel, malformed rewrite/health/status metadata, dialog focus and 320px layout passed (mock model).')

if __name__ == '__main__':
    asyncio.run(main())
