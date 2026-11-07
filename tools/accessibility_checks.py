"""Automated WCAG checks. This is not a substitute for assistive-technology review."""
import asyncio
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright
from browser_fixtures import detection_fixture, USAGE_FIXTURE, USAGE_TOTALS_FIXTURE


async def main():
    out = Path('artifacts')
    out.mkdir(exist_ok=True)
    axe = Path('node_modules/axe-core/axe.min.js').read_text(encoding='utf8')
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=os.getenv('TEXTLAB_BROWSER_EXECUTABLE') or None)
        page = await browser.new_page()
        await page.route('**/api/health', lambda route: route.fulfill(json={'provider':'ollama','model':'unavailable-test','auth_required':False}))
        await page.route('**/api/provider-status', lambda route: route.fulfill(json={'ready':False,'verified':False,'message':'Ingen testmodell.'}))
        await page.route('**/api/usage', lambda route: route.fulfill(json=USAGE_TOTALS_FIXTURE))
        async def detector(route):
            await route.fulfill(json=detection_fixture(route.request.post_data_json['text'], verified=True))
        await page.route('**/api/detect', detector)
        await page.goto(os.getenv('TEXTLAB_TEST_URL','http://127.0.0.1:8767'),wait_until='networkidle')
        for width in [1440, 390, 320]:
            await page.set_viewport_size({'width':width,'height':900})
            for mode in ['AI-detektor','AI-humanizer']:
                await page.get_by_role('button',name=mode).click()
                await page.evaluate(axe)
                report = await page.evaluate("""async () => {
                    const r = await axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}});
                    return {violations:r.violations.map(v=>({id:v.id,impact:v.impact,help:v.help,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),passes:r.passes.length,incomplete:r.incomplete.length,incompleteChecks:r.incomplete.map(v=>({id:v.id,impact:v.impact,help:v.help,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))};
                }""")
                report.update(width=width, mode=mode)
                results.append(report)
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Overflow at {width}px'
        original='Vi betalade 125 kr. Det här är originalet.'
        rewritten='Vi har betalat 125 kr. Det här är originalet.'
        await page.route('**/api/rewrite',lambda route:route.fulfill(json={'text':rewritten,'diff':[{'kind':'delete','text':original},{'kind':'insert','text':rewritten}],'protected_count':1,'provider':'mock','model':'accessibility-fixture','warning':'Granska textens betydelse.','usage':USAGE_FIXTURE}))
        for width in [1440,320]:
            await page.set_viewport_size({'width':width,'height':900})
            for mode in ['AI-detektor','AI-humanizer']:
                await page.get_by_role('button',name=mode).click()
                if mode=='AI-detektor':
                    await page.get_by_role('button',name='Prova ett exempel').click()
                    editor = page.get_by_role('textbox',name='Din originaltext',exact=True)
                    await editor.fill(await editor.input_value() + '\n\nKort.')
                    await page.get_by_role('button',name='Analysera text',exact=True).click()
                    await page.locator('.annotated-source').wait_for()
                    await page.locator('.style-details > summary').click()
                    await page.locator('.evidence > summary').click()
                    await page.locator('.method-details > summary').click()
                    await page.locator('.segment-navigation > summary').click()
                    await page.locator('.source-segment.uncertain').click()
                else:
                    await page.get_by_role('combobox',name='Textens språk').select_option('sv')
                    await page.get_by_role('textbox',name='Din originaltext',exact=True).fill(original)
                    await page.get_by_role('button',name='Skriv om med AI',exact=True).click()
                    await page.locator('.output').wait_for()
                    await page.get_by_label('Visa ändringar').check()
                    await page.locator('.original-comparison summary').click()
                    await page.locator('.usage-details > summary').click()
                    if not await page.locator('.aggregate-usage').evaluate('(element) => element.open'):
                        await page.locator('.aggregate-usage > summary').click()
                report=await page.evaluate("""async () => {
                    const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}});
                    return {violations:r.violations.map(v=>({id:v.id,impact:v.impact,help:v.help,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),passes:r.passes.length,incomplete:r.incomplete.length,incompleteChecks:r.incomplete.map(v=>({id:v.id,impact:v.impact,help:v.help,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))};
                }""")
                results.append(dict(report,width=width,mode=mode+'-result'))
                if report['incomplete']:
                    await page.screenshot(path=str(out/f'accessibility-{mode}-{width}.png'),full_page=True)
                assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Result overflow at {width}px'
        await page.set_viewport_size({'width':1440,'height':900})
        await page.get_by_role('button',name='Inställningar').click()
        await page.evaluate(axe)
        dialog = await page.evaluate("""async () => {
            const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}});
            return {violations:r.violations.map(v=>({id:v.id,impact:v.impact,help:v.help,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),passes:r.passes.length,incomplete:r.incomplete.length,incompleteChecks:r.incomplete.map(v=>({id:v.id,impact:v.impact,help:v.help,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))};
        }""")
        results.append(dict(dialog, mode='settings',width=1440))
        await page.keyboard.press('Escape')
        assert await page.get_by_role('button',name='Inställningar').evaluate('(el)=>el===document.activeElement'), 'Dialog must restore focus'
        await browser.close()
    report={'engine':'axe-core','screens':results,'violations':sum(len(r['violations']) for r in results),'manualScreenReaderReview':'not_performed'}
    (out/'accessibility.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    assert report['violations']==0, f"{report['violations']} automated accessibility violations; inspect artifacts/accessibility.json"


if __name__=='__main__':
    asyncio.run(main())
