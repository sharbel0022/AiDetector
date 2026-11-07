"""V5 browser contracts: real local detector plus labeled UI/provider fixtures."""
import asyncio
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright, expect
from browser_fixtures import detection_fixture, USAGE_FIXTURE, USAGE_TOTALS_FIXTURE


async def main():
    out = Path('artifacts'); out.mkdir(exist_ok=True)
    checks = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=os.getenv('TEXTLAB_BROWSER_EXECUTABLE') or None)
        page = await browser.new_page(viewport={'width': 1440, 'height': 1050}, device_scale_factor=1)
        errors, posted = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: posted.append(request.url) if request.method == 'POST' else None)
        await page.route('**/api/health', lambda route: route.fulfill(json={'provider': 'ollama', 'model': 'test-model', 'auth_required': False}))
        await page.route('**/api/provider-status', lambda route: route.fulfill(json={'ready': False, 'verified': False, 'message': 'Test: riktig modell är inte ansluten.'}))
        await page.route('**/api/usage', lambda route: route.fulfill(json=USAGE_TOTALS_FIXTURE))
        async def unvalidated(route):
            assert route.request.post_data_json['language'] == 'auto'
            await route.fulfill(json=detection_fixture(route.request.post_data_json['text'], raw_unvalidated_scores=True))
        await page.route('**/api/detect', unvalidated)
        await page.goto(os.getenv('TEXTLAB_TEST_URL', 'http://127.0.0.1:8767'), wait_until='networkidle')
        await page.get_by_role('heading', name='Din text. Din röst.').wait_for()
        await page.screenshot(path=str(out / 'desktop.png'), full_page=True)
        checks.append('page loads with local assets and explicit server/local processing description')
        await page.get_by_role('button', name='Prova ett exempel').click()
        await page.get_by_role('button', name='Analysera text', exact=True).click()
        await page.locator('.detector-summary').wait_for()
        await expect(page.locator('.document-probability')).to_have_text('—')
        await expect(page.locator('.ai-marked-share')).to_have_text('—')
        assert len(posted) == 1 and posted[0].endswith('/api/detect')
        await expect(page.locator('.source-segment.ai_like')).to_have_count(0)
        await page.locator('.style-details > summary').click()
        assert await page.locator('.score').inner_text() != '—'
        await expect(page.locator('.evidence-source')).to_have_attribute('lang', 'sv')
        await expect(page.get_by_text('Författarskap: kan inte avgöras.', exact=True)).to_be_visible()
        checks.append('server detection is explicit; unvalidated raw scores cannot appear as percentages or highlights')
        await page.screenshot(path=str(out / 'analysis.png'), full_page=True)

        editor = page.get_by_role('textbox', name='Din originaltext', exact=True)
        # Exercise the built frontend against the real running FastAPI detector.
        # This validates integration, not the historical model's accuracy.
        await page.unroute('**/api/detect')
        actual_source = await editor.input_value()
        async with page.expect_response(lambda response: response.url.endswith('/api/detect') and response.request.method == 'POST') as response_info:
            await page.get_by_role('button', name='Analysera text', exact=True).click()
        actual_response = await response_info.value
        assert actual_response.status == 200
        actual_result = await actual_response.json()
        assert actual_result['detector']['modelVersion'].startswith('textlab-v5-')
        assert actual_result['detector']['documentValidated'] is False
        assert actual_result['detector']['segmentValidated'] is False
        await expect(page.locator('.detector-model strong')).to_have_text(actual_result['detector']['modelVersion'])
        await expect(page.locator('.document-probability')).to_have_text('—')
        await expect(page.locator('.ai-marked-share')).to_have_text('—')
        await expect(page.locator('.annotated-source')).to_have_text(actual_source)
        await expect(page.locator('.source-segment.ai_like')).to_have_count(0)
        await page.screenshot(path=str(out / 'real-detector-v5.png'), full_page=True)
        checks.append('built frontend integrates with actual FastAPI V5 model, exact source and closed evidence gates')
        await page.route('**/api/detect', unvalidated)
        await editor.fill('En kort text med ett tydligt budskap.')
        await expect(page.locator('.detector-summary')).to_have_count(0)
        await expect(page.locator('.source-review')).to_have_count(0)
        await page.get_by_role('button', name='Analysera text', exact=True).click()
        await expect(page.locator('.assessment-badge')).to_have_text('Otillräckligt underlag')
        await page.locator('.style-details > summary').click()
        await expect(page.locator('.score')).to_have_text('—')
        checks.append('editing invalidates the entire previous result and short text abstains')

        hostile = '<img src=x onerror=alert(1)> ' + 'Text med vanliga ord. ' * 30
        await editor.fill(hostile)
        await page.get_by_role('button', name='Analysera text', exact=True).click()
        await expect(page.locator('.annotated-source')).to_have_text(hostile)
        assert await page.locator('.annotated-source img').count() == 0
        await page.locator('.style-details > summary').click()
        await page.locator('.evidence > summary').click()
        assert await page.locator('.evidence img').count() == 0
        checks.append('untrusted full source and local evidence render as literal text')

        await page.unroute('**/api/detect')
        unicode_text = '🙂 Åsa läser ”texten” och skriver ett svar.\n\nThe text is clear and the reader can follow the words.\n\nDet här stycket är osäkert.\n\nKort.'
        async def verified(route):
            await route.fulfill(json=detection_fixture(route.request.post_data_json['text'], verified=True))
        await page.route('**/api/detect', verified)
        await editor.fill(unicode_text)
        await page.get_by_role('button', name='Analysera text', exact=True).click()
        await expect(page.locator('.document-probability')).to_have_text('72 %')
        assert await page.locator('.ai-marked-share').inner_text() != '—'
        await expect(page.locator('.annotated-source')).to_have_text(unicode_text)
        for category in ['ai_like', 'human_like', 'uncertain', 'unassessed']:
            await expect(page.locator('.source-segment.' + category)).to_have_count(1)
        segment = page.locator('.source-segment.human_like')
        await segment.focus(); await page.keyboard.press('Enter')
        await expect(page.locator('#segment-detail h3')).to_have_text('Mänskligt-liknande')
        await expect(page.locator('#segment-detail')).to_contain_text('Ej tillgängligt')
        checks.append('independently validated document/share, four labels, exact Unicode source, keyboard segment details and separate segment-calibration gate')
        for kind in ['TXT', 'JSON']:
            async with page.expect_download() as download_info:
                await page.get_by_role('button', name='Rapport ' + kind, exact=True).click()
            download = await download_info.value
            report = Path(await download.path()).read_text(encoding='utf8')
            assert download.suggested_filename == 'textlab-analys.' + kind.lower()
            if kind == 'JSON':
                parsed = json.loads(report)
                assert parsed['sourceText'] == unicode_text and parsed['detector']['documentProbability'] == .72
                assert parsed['segments'][0]['probability'] is None
                assert 'definitions' in parsed and 'limitation' in parsed
            else:
                assert unicode_text in report and 'inte bevis' in report
        await page.evaluate('window.print = () => { window.__printed = true; }')
        await page.get_by_role('button', name='Skriv ut / PDF', exact=True).click()
        assert await page.evaluate('window.__printed === true')
        checks.append('TXT/JSON reports retain source, model, definitions, flags and limitations; print invokes browser print')
        await page.emulate_media(media='print')
        await page.pdf(path=str(out / 'analysis-report-v5-fixture.pdf'), format='A4', print_background=True)
        await page.emulate_media(media='screen')
        await page.screenshot(path=str(out / 'segments-v5.png'), full_page=True)
        for width in [390, 320]:
            await page.set_viewport_size({'width': width, 'height': 900})
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await page.screenshot(path=str(out / f'segments-v5-mobile-{width}.png'), full_page=True)
        await page.set_viewport_size({'width': 1440, 'height': 1050})

        english = 'The text is clear and the reader can understand what the writer means. It is a useful example of the way we use language.'
        await editor.fill(english)
        await page.get_by_role('combobox', name='Textens språk').select_option('sv')
        await expect(page.locator('#language-feedback')).to_contain_text('engelska')
        await expect(page.locator('#language-feedback')).to_contain_text('men svenska är valt')
        await page.get_by_role('combobox', name='Textens språk').select_option('auto')
        await expect(page.locator('#language-feedback')).to_contain_text('Identifierat språk: engelska')
        checks.append('auto language follows English input and manual mismatch is visible')

        await page.unroute('**/api/detect')
        async def slow_detection(route):
            text = route.request.post_data_json['text']
            await asyncio.sleep(.4)
            try: await route.fulfill(json=detection_fixture(text, verified=True))
            except Exception: pass
        await page.route('**/api/detect', slow_detection)
        await page.get_by_role('button', name='Analysera text', exact=True).click()
        await editor.fill('Ny text som inte får ersättas av ett gammalt resultat.')
        await page.wait_for_timeout(650)
        await expect(page.locator('.detector-summary')).to_have_count(0)
        checks.append('late detection replies cannot publish results for changed input')
        await page.unroute('**/api/detect')
        await page.route('**/api/detect', lambda route: route.fulfill(status=503, json={'detail':'Detektorn är inte tillgänglig.'}))
        await page.get_by_role('button', name='Analysera text', exact=True).click()
        await expect(page.locator('.error')).to_contain_text('Detektorn är inte tillgänglig')
        await expect(page.locator('.document-probability')).to_have_count(0)
        await expect(page.locator('.local-only')).to_be_visible()
        checks.append('detector failure keeps source and exposes local style without fabricated AI output')

        await page.get_by_role('button', name='AI-humanizer').click()
        await page.get_by_role('combobox', name='Textens språk').select_option('sv')
        await editor.fill('Vi betalade 125 kr. Det här är originalet.')
        async def success(route):
            body = route.request.post_data_json
            assert body['tone'] == 'natural' and body['language'] == 'sv'
            await route.fulfill(json={'text':'Vi har betalat 125 kr. Det här är originalet.','provider':'mock','model':'test-only','protected_count':1,'warning':'Testresultat, inte verifierad modellkvalitet.','diff':[{'kind':'equal','text':'Vi '},{'kind':'delete','text':'betalade'},{'kind':'insert','text':'har betalat'},{'kind':'equal','text':' 125 kr. Det här är originalet.'}],'usage':USAGE_FIXTURE})
        await page.route('**/api/rewrite', success)
        await page.get_by_role('button', name='Skriv om med AI', exact=True).click()
        await page.locator('.output').wait_for()
        await page.get_by_label('Visa ändringar').check()
        assert await page.locator('.output ins').count() == 1
        await page.locator('.original-comparison summary').click()
        await expect(page.locator('.original-snapshot')).to_have_text('Vi betalade 125 kr. Det här är originalet.')
        await page.locator('.usage-details > summary').click()
        await expect(page.locator('.usage-details')).to_contain_text('0,001 USD')
        await page.locator('.aggregate-usage > summary').click()
        await expect(page.locator('.aggregate-usage')).to_contain_text('ofullständig summa')
        await page.screenshot(path=str(out / 'humanizer-v5.png'), full_page=True)
        checks.append('humanizer keeps original/diff and distinguishes usage, estimated cost and incomplete totals')
        await page.unroute('**/api/usage')
        legacy_totals = {**USAGE_TOTALS_FIXTURE, 'legacy_usage_unavailable': True,
                         'unreported_counters': {key: 0 for key in USAGE_TOTALS_FIXTURE['unreported_counters']},
                         'estimated_cost': {**USAGE_TOTALS_FIXTURE['estimated_cost'], 'unknown_requests': 0},
                         'reservations': {'legacy_reserved_tokens': 5000}}
        await page.route('**/api/usage', lambda route: route.fulfill(json=legacy_totals))
        await page.get_by_role('button', name='Skriv om med AI', exact=True).click()
        await expect(page.locator('.aggregate-usage')).to_contain_text('Förbrukning från äldre anrop är inte tillgänglig')
        await expect(page.locator('.aggregate-usage .usage-grid dd')).to_have_text(['125 · ofullständig summa', '0,001 USD · ofullständig summa'])
        checks.append('legacy ledger records keep token and cost totals incomplete even with zero current missing counters')
        await page.unroute('**/api/rewrite')
        async def slow_rewrite(route):
            await asyncio.sleep(.4)
            try: await route.fulfill(json={'text':'STALE','diff':[],'protected_count':0})
            except Exception: pass
        await page.route('**/api/rewrite', slow_rewrite)
        await page.get_by_role('button', name='Skriv om med AI', exact=True).click()
        await editor.fill('Ny originaltext som inte får skrivas över.')
        await page.wait_for_timeout(650)
        await expect(page.locator('.output')).to_have_count(0)
        checks.append('late rewrite replies cannot overwrite changed input')
        await page.unroute('**/api/rewrite')
        await page.route('**/api/rewrite', lambda route: route.fulfill(status=503, json={'detail':'Modellen är inte tillgänglig.'}))
        await page.get_by_role('button', name='Skriv om med AI', exact=True).click()
        await expect(page.locator('.error')).to_contain_text('Modellen är inte tillgänglig')
        await expect(page.locator('.output')).to_have_count(0)
        checks.append('provider failure is an error, not a fake rewrite')
        await page.get_by_role('button', name='Inställningar').click()
        await page.get_by_label('TextLab-åtkomstkod').fill('test-only-token')
        await page.get_by_role('button', name='Anslut', exact=True).click()
        assert await page.evaluate('Object.values(localStorage).join("")') == ''
        assert await page.evaluate('Object.values(sessionStorage).join("")') == ''
        checks.append('access token is not persisted in browser storage')
        await page.get_by_role('button', name='AI-detektor').click()
        for width in [390, 320]:
            await page.set_viewport_size({'width': width, 'height': 844})
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await page.screenshot(path=str(out / 'mobile.png'), full_page=True)
        assert not errors, errors
        checks.append('mobile layouts have no horizontal overflow and no uncaught JavaScript errors')
        await browser.close()
    report = {'checks_passed':len(checks),'checks':checks,'detector_responses':'mocked','llm_responses':'mocked','live_model_verified':False,'sites_publication_verified':False}
    (out / 'browser-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
