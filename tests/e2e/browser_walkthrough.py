# End-to-end browser walkthrough (47 checks). Needs: `uv run casebreak serve --port 8811`, Playwright with Chromium,
# and a synthetic dossier: `uv run casebreak synth --out <dir>/synth7 --seed 7`. Run: python browser_walkthrough.py <dir>
import re, sys, json, time
from playwright.sync_api import sync_playwright, expect
SP = sys.argv[1]; B = "http://localhost:8811"
errors, results = [], []
def ok(name, cond, info=""):
    results.append((name, bool(cond), info)); print(("PASS " if cond else "FAIL ") + name, info)

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": 1600, "height": 1000}, accept_downloads=True)
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(f"PAGEERROR {e}"))
    pg.on("console", lambda m: errors.append(f"console.{m.type}: {m.text} @ {m.location.get('url')}") if m.type == "error" else None)
    pg.on("response", lambda r: errors.append(f"HTTP {r.status} {r.url}") if r.status >= 400 and "fonts/ALTMistral" not in r.url else None)

    # 1. landing
    pg.goto(B + "/")
    ok("landing en français", "Trouver le" in pg.inner_text("h1"))
    # 2. upload through the drop zone
    pg.set_input_files("#file-input", [f"{SP}/synth7/dossier.pdf"])
    pg.wait_for_selector("#files:not([hidden])")
    ok("fichier listé", "dossier.pdf" in pg.inner_text("#file-list"))
    pg.click("#analyze")
    pg.wait_for_url(re.compile(r"app\.html\?case=c"), timeout=15000)
    ok("redirection salle des opérations après dépôt", True, pg.url)
    pg.wait_for_selector("#war-open:not([disabled])", timeout=60000)
    ok("dépôt analysé", "nullités possibles" in pg.inner_text("#war-title"), pg.inner_text("#war-title"))

    # 3. demo from landing
    pg.goto(B + "/")
    pg.click("#demo")
    pg.wait_for_url(re.compile(r"case=demo-"), timeout=15000)
    pg.wait_for_timeout(4000)
    pages_mid = int(pg.inner_text('[data-k="pages"] .counter__n'))
    ok("compteurs vivants pendant l'analyse", pages_mid > 0, f"pages lues à 4 s : {pages_mid}")
    pg.wait_for_selector("#war-open:not([disabled])", timeout=90000)
    c = {k: int(pg.inner_text(f'[data-k="{k}"] .counter__n')) for k in ["pages", "pieces", "possible_nullity"]}
    ok("compteurs finaux", c["pages"] == 120 and c["pieces"] == 53 and c["possible_nullity"] == 10, str(c))
    ok("flux contient des alertes", pg.locator(".stream__log li.k-alert").count() >= 10)
    case = re.search(r"case=([\w-]+)", pg.url).group(1)
    pg.click("#war-open")
    pg.wait_for_selector(".al")

    # 4. timeline
    ok("frise : couloirs", pg.locator(".lane-label").count() >= 8, str(pg.locator(".lane-label").count()))
    ok("frise : nœuds", pg.locator(".t-node").count() >= 40, str(pg.locator(".t-node").count()))
    ok("frise : nullités en rouge", pg.locator(".t-node.pn").count() >= 6)
    ok("frise : contradictions", pg.locator(".t-con").count() >= 2)
    ok("frise : barres de GAV", pg.locator(".t-custody").count() == 3)
    ok("liste : 16 alertes", pg.locator(".al").count() == 16, str(pg.locator(".al").count()))
    ok("délai J-", re.search(r"J-\d+", pg.inner_text("#deadline")) is not None, pg.inner_text(".deadline__row")[:60])
    pg.wait_for_timeout(2500)
    ok("tampons du tribunal préchargés", pg.locator(".al .stamp").count() >= 10)
    # hover tooltip
    pg.hover(".t-node.pn .shape >> nth=0")
    ok("infobulle", pg.is_visible("#tooltip"))
    # zoom
    w0 = pg.eval_on_selector("#timeline", "e => +e.getAttribute('width')")
    pg.click("#zoom-in"); w1 = pg.eval_on_selector("#timeline", "e => +e.getAttribute('width')")
    ok("zoom", w1 > w0, f"{w0}→{w1}")
    pg.click("#zoom-out")
    # filters
    pg.click('#filters button[data-f="needs_reading"]'); n_nr = pg.locator(".al").count()
    pg.click('#filters button[data-f="possible_nullity"]'); n_pn = pg.locator(".al").count()
    pg.click('#filters button[data-f="all"]')
    ok("filtres", n_nr == 6 and n_pn == 10, f"à lire {n_nr}, possibles {n_pn}")

    # 5. node drawer
    pg.locator(".t-node.pn .shape").first.click()
    pg.wait_for_selector("#node-drawer:not([hidden])")
    ok("tiroir d'acte : liste de contrôle + attributs avec citation", pg.locator(".checklist li").count() >= 1 and pg.locator(".attrs .q").count() >= 1)
    pg.click(".nd__close")

    # 6. alert card GAV-04
    pg.locator(".al", has_text="GAV-04").first.click()
    pg.wait_for_selector(".ac__head h2")
    ok("carte : titre", "Notification des droits" in pg.inner_text(".ac__head h2"))
    ok("carte : 4 questions", pg.locator(".q4--what, .q4--where, .q4--why, .q4--next").count() == 4)
    pg.wait_for_selector(".pv__page img", timeout=10000)
    pg.wait_for_function("document.querySelector('.pv__page img').naturalWidth > 0")
    pg.wait_for_selector(".pv__hl", timeout=5000)
    ok("page affichée + surlignage", pg.locator(".pv__hl").count() >= 1)
    ok("annotation 3 h 15", "3 h 15" in pg.inner_text(".pv__page"))
    pg.locator(".pv__tabs button").nth(1).click(); pg.wait_for_timeout(1200)
    ok("seconde source (p. 7) surlignée", pg.locator(".pv__hl").count() >= 1 and "p. 7" in pg.inner_text(".pv__tabs button.is-on"))
    pg.click("#pv-text"); ok("texte lu", pg.locator(".pv__text").count() == 1); pg.click("#pv-text")
    pg.wait_for_selector(".bubble--pres", timeout=10000)
    ok("tribunal : verdict survit", "survit" in pg.inner_text(".bubble--pres").lower())
    pg.wait_for_selector(".proof", timeout=20000)
    ok("preuve Lean vérifiée", "prouvé" in pg.inner_text(".proof-head").lower(), pg.inner_text(".proof-head"))
    ok("précédents : honnête sans clé", "JUDILIBRE_KEY_ID" in pg.inner_text("#prec"))
    ok("contre-arguments", pg.locator("#counter-args li").count() >= 2)
    pg.fill(".q4--next textarea", "test e2e")
    pg.click("text=✓ Retenir"); pg.wait_for_timeout(800)
    ok("revue enregistrée", "retenu" in pg.inner_text(".review").lower())
    pg.keyboard.press("Escape"); pg.wait_for_timeout(1200)
    ok("pastille « retenu » dans la liste", pg.locator(".al .pill--acc").count() >= 1)

    # 7. decoy GAV-05 → tribunal fragilises
    pg.locator(".al", has_text="GAV-05").first.click()
    pg.wait_for_selector(".bubble--pres", timeout=10000)
    ok("leurre : moyen fragilisé (pièce du parquet)", "fragilis" in pg.inner_text(".bubble--pres").lower(), pg.inner_text(".bubble--pres .stamp"))
    ok("juge zone grise affiché", pg.locator(".q4--judge").count() == 1)
    pg.keyboard.press("Escape")

    # 8. domino
    pg.locator(".al", has_text="PRQ-01").first.click()
    pg.wait_for_selector(".ac__actions .btn--primary"); pg.click(".ac__actions .btn--primary")
    pg.wait_for_timeout(3500)
    ok("domino : 8 actes tombés", pg.locator(".t-node.fallen").count() == 8 and pg.inner_text("#domino-n") == "8", f"{pg.locator('.t-node.fallen').count()} / {pg.inner_text('#domino-n')}")
    ok("domino : liste des actes à viser", pg.locator("#node-drawer .casc li").count() == 8)
    pg.screenshot(path=f"{SP}/e2e_domino.png")
    pg.click("text=Rétablir le dossier")
    ok("rétablir", pg.locator(".t-node.fallen").count() == 0 and pg.is_hidden("#domino-sticker"))

    # 9. time travel
    pg.click('#asof-seg button[data-asof="fixed"]'); pg.wait_for_timeout(2000)
    n_old = pg.locator(".al").count(); pn_old = pg.inner_text("#alerts-hand")
    ok("droit au 01/06/2023 : GAV-08 disparaît", "9 possibles" in pn_old and pg.locator(".al", has_text="GAV-08").count() == 0, pn_old)
    pg.click('#asof-seg button[data-asof="auto"]'); pg.wait_for_timeout(1500)
    ok("retour au droit de chaque acte", "10 possibles" in pg.inner_text("#alerts-hand"))

    # 10. parquet + pseudo
    pg.click('#mode-seg button[data-mode="parquet"]'); pg.wait_for_timeout(1500)
    pg.locator(".al").first.click(); pg.wait_for_selector(".ac__headline")
    ok("mode parquet", "régularité" in pg.inner_text(".ac__headline").lower())
    pg.keyboard.press("Escape")
    pg.click('#mode-seg button[data-mode="defense"]')
    pg.click("#pseudo-toggle"); pg.wait_for_timeout(1500)
    txt = pg.inner_text("#alert-list")
    ok("pseudonymisation", "VASSEUR" not in txt and "[NOM_" in txt)
    pg.click("#pseudo-toggle"); pg.wait_for_timeout(1000)

    # 11. alerts table
    pg.click('a[data-view="alerts"]'); pg.wait_for_timeout(500)
    ok("vue alertes : tableau", pg.locator("#dense tbody tr").count() == 16)

    # 12. report
    pg.click('a[data-view="report"]'); pg.wait_for_selector("#report h1", timeout=20000)
    ok("rapport : moyens", "Moyens de nullité" in pg.inner_text("#report h1") and "retenu par l'avocat" in pg.inner_text("#report"))
    with pg.expect_download() as d: pg.click("#dl-pdf")
    pdfp = f"{SP}/e2e_report.pdf"; d.value.save_as(pdfp)
    ok("PDF téléchargé", open(pdfp, "rb").read(4) == b"%PDF")
    with pg.expect_download() as d: pg.click("#dl-md")
    d.value.save_as(f"{SP}/e2e_report.md"); ok("Markdown téléchargé", "Moyens" in open(f"{SP}/e2e_report.md").read())

    # 13. bench
    pg.click('a[data-view="bench"]'); pg.wait_for_timeout(1000)
    pg.click("#bench-run")
    pg.wait_for_function("document.querySelector('#bench-state').textContent === '' && document.querySelector('.kpis')", timeout=180000)
    ok("banc : KPIs", pg.locator(".kpi").count() == 5, pg.inner_text(".kpis").replace("\n", " ")[:120])
    with pg.expect_download() as d: pg.click("text=Exporter NullityBench-FR")
    d.value.save_as(f"{SP}/e2e_bench.zip"); ok("export zip", open(f"{SP}/e2e_bench.zip", "rb").read(2) == b"PK")

    # 14. picker
    pg.goto(B + "/app.html"); pg.wait_for_selector("#picker-list li", timeout=10000)
    ok("sélecteur de dossiers", pg.locator("#picker-list li").count() >= 2)
    br.close()

fails = [r for r in results if not r[1]]
print(f"\n{len(results) - len(fails)}/{len(results)} PASS")
print("ERREURS NAVIGATEUR:", len(errors)); print("\n".join(errors[:20]))
