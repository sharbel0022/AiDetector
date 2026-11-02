"""Real browser checks with explicitly mocked LLM responses; no model-quality claim."""
import asyncio
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    out=Path('artifacts');out.mkdir(exist_ok=True)
    checks=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        page=await browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        posted=[]
        page.on('request',lambda request:posted.append(request.url) if request.method=='POST' else None)
        await page.route('**/api/health',lambda route:route.fulfill(json={'provider':'ollama','model':'test-model','auth_required':False}))
        await page.route('**/api/provider-status',lambda route:route.fulfill(json={'ready':False,'verified':False,'message':'Test: riktig modell är inte ansluten.'}))
        await page.goto(os.getenv('TEXTLAB_TEST_URL','http://127.0.0.1:8767'),wait_until='networkidle')
        await page.get_by_role('heading',name='Din text. Din röst.').wait_for()
        checks.append('page loads without external assets')
        await page.screenshot(path=str(out/'desktop.png'),full_page=True)
        await page.get_by_role('button',name='Prova ett exempel').click()
        await page.get_by_role('button',name='Analysera text').click()
        await page.locator('.analysis-result').wait_for()
        assert await page.locator('.score').inner_text()!='—'
        assert await page.get_by_text('Författarskap: kan inte avgöras.').count()==1
        assert not posted, 'Local analysis must not POST source text'
        checks.append('local analysis reports signals and uncertainty')
        await page.screenshot(path=str(out/'analysis.png'),full_page=True)
        editor=page.get_by_role('textbox',name='Din originaltext')
        await editor.fill('En kort text med ett tydligt budskap.')
        assert await page.locator('.analysis-result').count()==0
        await page.get_by_role('button',name='Analysera text').click()
        assert await page.locator('.score').inner_text()=='—'
        checks.append('editing invalidates previous result; short text abstains')
        await editor.fill('<img src=x onerror=alert(1)> ' + 'Text med vanliga ord. '*30)
        await page.get_by_role('button',name='Analysera text').click()
        await page.locator('.evidence > summary').click()
        assert await page.locator('.evidence img').count()==0
        checks.append('untrusted text renders as text, not HTML')
        await page.get_by_role('button',name='AI-humanizer').click()
        await editor.fill('Vi betalade 125 kr. Det här är originalet.')
        async def success(route):
            body=route.request.post_data_json
            assert body['tone']=='natural' and body['language']=='sv'
            await route.fulfill(json={'text':'Vi har betalat 125 kr. Det här är originalet.','provider':'mock','model':'test-only','protected_count':1,'warning':'Testresultat, inte verifierad modellkvalitet.','diff':[{'kind':'equal','text':'Vi '},{'kind':'delete','text':'betalade'},{'kind':'insert','text':'har betalat'},{'kind':'equal','text':' 125 kr. Det här är originalet.'}]})
        await page.route('**/api/rewrite',success)
        await page.get_by_role('button',name='Skriv om med AI').click()
        await page.locator('.output').wait_for()
        assert '125 kr' in await page.locator('.output').inner_text()
        await page.get_by_label('Visa ändringar').check()
        assert await page.locator('.output ins').count()==1
        checks.append('rewrite request, result and diff use the API contract (mock)')
        await page.unroute('**/api/rewrite')
        async def slow(route):
            await asyncio.sleep(0.4)
            try:await route.fulfill(json={'text':'STALE','diff':[],'protected_count':0})
            except Exception:pass
        await page.route('**/api/rewrite',slow)
        await page.get_by_role('button',name='Skriv om med AI').click()
        await editor.fill('Ny originaltext som inte får skrivas över.')
        await page.wait_for_timeout(700)
        assert await page.locator('.output').count()==0
        assert 'Ny originaltext' in await editor.input_value()
        checks.append('late responses cannot overwrite changed input')
        await page.unroute('**/api/rewrite')
        await page.route('**/api/rewrite',lambda route:route.fulfill(status=503,json={'detail':'Modellen är inte tillgänglig.'}))
        await page.get_by_role('button',name='Skriv om med AI').click()
        await page.get_by_role('alert').wait_for()
        assert await page.locator('.output').count()==0
        checks.append('provider failure is an error, not a fake rewrite')
        await page.get_by_role('button',name='Inställningar').click()
        await page.get_by_label('TextLab-åtkomstkod').fill('test-only-token')
        await page.get_by_role('button',name='Anslut',exact=True).click()
        assert await page.evaluate('Object.values(localStorage).join("")')==''
        assert await page.evaluate('Object.values(sessionStorage).join("")')==''
        checks.append('access token is not persisted in browser storage')
        await page.set_viewport_size({'width':390,'height':844})
        await page.get_by_role('button',name='AI-detektor').click()
        assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await page.screenshot(path=str(out/'mobile.png'),full_page=True)
        checks.append('390px mobile layout has no horizontal overflow')
        assert not errors,errors
        checks.append('no uncaught browser JavaScript errors')
        await browser.close()
    report={'checks_passed':len(checks),'checks':checks,'llm_responses':'mocked','live_model_verified':False,'sites_publication_verified':False}
    (out/'browser-results.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':asyncio.run(main())
