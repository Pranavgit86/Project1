get_ipython().system('pip install playwright beautifulsoup4 nest_asyncio -q')
get_ipython().system('playwright install chromium')
get_ipython().system('playwright install-deps chromium')
import asyncio
import nest_asyncio
nest_asyncio.apply()
import random
import re
import subprocess
import platform

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from urllib.parse import urlparse, parse_qs, unquote

import ipywidgets as widgets
from IPython.display import display, clear_output

SERVICES = {
    "Mobile App Developers":  "https://clutch.co/directory/mobile-application-developers",
    "Web Developers":          "https://clutch.co/directory/web-developers",
    "Software Developers":     "https://clutch.co/developers",
    "Ecommerce Developers":    "https://clutch.co/developers/ecommerce",
    "UI/UX Agencies":          "https://clutch.co/agencies/ui-ux",
    "SEO Firms":               "https://clutch.co/seo-firms",
    "IT Services":             "https://clutch.co/it-services",
}

def get_company_website(card):
    tag = card.select_one("a.provider__cta-link.website-link__item.website-link__item--non-ppc")
    if not tag:
        return ""
    href = tag.get("href", "")
    if not href:
        return ""
    qs = parse_qs(urlparse(href).query)
    if "u" in qs:
        return unquote(qs["u"][0])
    return href

def get_total_count(soup):
    tag = soup.select_one("p.navbar__companies-amount.directory-only-related-block")
    return tag.get_text(strip=True) if tag else "N/A"

def parse_html(html, service_name, category_url):
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    print("  Total on Clutch: " + get_total_count(soup))
    provider_list = soup.select_one("ul.providers__list")
    if not provider_list:
        print("  No provider list found")
        return []
    cards = provider_list.select("li.provider-list-item")
    print("  Cards on this page: " + str(len(cards)))
    results = []
    for card in cards:
        try:
            name_tag = card.select_one("h3.provider__title")
            company_name = name_tag.get_text(strip=True) if name_tag else ""
            profile_tag = card.select_one('a[href^="/profile/"]')
            company_url = ("https://clutch.co" + profile_tag.get("href", "") if profile_tag else "")
            company_website = get_company_website(card)
            if company_name:
                results.append({
                    "company_name":    company_name,
                    "company_url":     company_url,
                    "company_website": company_website,
                    "source_category": service_name,
                })
        except Exception as e:
            print("  Skipped card: " + str(e))
    return results

import random

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--window-size=1440,900",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

STEALTH_JS = """
Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
window.chrome={runtime:{}};
"""

def build_page_url(base_url, page_num):
    if page_num == 1:
        return base_url
    sep = "&" if "?" in base_url else "?"
    return base_url + sep + "page=" + str(page_num)

async def render_page(pw, url):
    """Fresh browser + context for every single page load"""
    print("  Opening : " + url)
    try:
        browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="America/New_York",
        )
        await context.add_init_script(STEALTH_JS)
        page = await context.new_page()

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        for selector in ["ul.providers__list", "li.provider-list-item", "[class*='providers']"]:
            try:
                await page.wait_for_selector(selector, timeout=15000)
                break
            except PWTimeout:
                continue
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.5)
        html = await page.content()

        await context.close()
        await browser.close()
        return html
    except PWTimeout:
        print("  Timeout : " + url)
        return ""
    except Exception as e:
        print("  Error : " + str(e))
        return ""

async def run_extraction(selected_services, max_pages):
    all_companies = []
    seen_urls = set()
    total_services = len(selected_services)

    async with async_playwright() as pw:
        for i, (service_name, base_url) in enumerate(selected_services.items(), 1):
            print("\n[" + str(i) + "/" + str(total_services) + "] " + service_name)

            for p in range(1, max_pages + 1):
                url = build_page_url(base_url, p)
                print("\n  Page " + str(p) + "/" + str(max_pages))
                html = await render_page(pw, url)
                companies = parse_html(html, service_name, base_url)
                if not companies:
                    print("  No companies found - stopping pagination")
                    break
                for c in companies:
                    key = c.get("company_url") or c.get("company_name", "")
                    if key and key not in seen_urls:
                        seen_urls.add(key)
                        all_companies.append(c)
                print("  Running total: " + str(len(all_companies)))
                delay = random.uniform(2, 4)
                await asyncio.sleep(delay)

            if i < total_services:
                delay = random.uniform(3, 5)
                print("\n  Waiting " + str(round(delay, 1)) + "s before next category...")
                await asyncio.sleep(delay)

    return all_companies

CONCURRENCY = 10
PAGE_TIMEOUT = 30000
SELECTOR_TIMEOUT = 8000
SCROLL_WAIT = 0.3
BLOCKED_RESOURCES = {"image", "media", "font", "stylesheet", "manifest", "other"}

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--window-size=1440,900",
]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]
STEALTH_JS = """
Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
window.chrome={runtime:{}};
"""


def _parse_chart_data(cj):
    if not cj or not isinstance(cj, dict): return {}
    r = {}
    def ex(s):
        items = []
        for x in s.get("slices", []):
            n = x.get("name", "")
            p = x.get("PercentHundreds", 0) or round(x.get("percent", 0)*100)
            if n: items.append({"name": n, "pct": f"{p}%" if p else ""})
        return items
    for k, s in cj.items():
        if not isinstance(s, dict): continue
        if "slices" in s:
            r[k] = {"title": s.get("legend_title", k), "items": ex(s)}
        if "charts" in s and isinstance(s["charts"], dict):
            for sk, ss in s["charts"].items():
                if isinstance(ss, dict) and "slices" in ss:
                    r[f"{k}__{sk}"] = {"title": ss.get("legend_title", sk), "items": ex(ss)}
    return r

def _map_charts(ch):
    d = {"services": [], "industry": [], "client_type": [], "focus_area": []}
    key_map = {
        "services":    ["service_provided", "services"],
        "industry":    ["industries", "industry"],
        "client_type": ["clients", "client_focus", "client_type", "client", "client_size"],
    }
    for field, candidates in key_map.items():
        for ck in candidates:
            if ck in ch:
                d[field] = ch[ck]["items"]
                break
    for k, v in ch.items():
        if k.startswith("focus__"):
            tl = v["title"].lower()
            if any(kw in tl for kw in ["client focus", "client type", "client size"]):
                if not d["client_type"]:
                    d["client_type"] = v["items"]
            else:
                d["focus_area"].append({"category": v["title"], "items": v["items"]})
    title_map = {
        "services":    ["service line"],
        "industry":    ["industry"],
        "client_type": ["client focus", "client type", "client size"],
    }
    for field, keywords in title_map.items():
        if d[field]: continue
        for k, v in ch.items():
            tl = v["title"].lower()
            if any(kw in tl for kw in keywords):
                d[field] = v["items"]
                break
    return d

def _charts_from_legends(soup):
    d = {"services": [], "industry": [], "client_type": [], "focus_area": []}
    sections = soup.select("section.profile-chart--section, div.profile-chart__wrapper, div.profile-chart")
    for sec in sections:
        te = sec.select_one("div.chart-legend--title, h3, h4, [class*='chart-title']")
        t = te.get_text(strip=True).lower() if te else ""
        items = []
        for li in sec.select("li.chart-legend--item"):
            name_tag = li.select_one("a.chart-legend--item-link")
            name = name_tag.get_text(strip=True) if name_tag else li.get_text(strip=True)
            full = li.get_text(strip=True)
            pct_match = re.search(r'(\d+%)', full)
            pct = pct_match.group(1) if pct_match else ""
            if name: items.append({"name": name, "pct": pct})
        if not items: continue
        if any(x in t for x in ["service", "line"]): d["services"] = items
        elif "industry" in t: d["industry"] = items
        elif "client" in t: d["client_type"] = items
        else: d["focus_area"].append({"category": t.title(), "items": items})
    return d


def _find_desc(soup):
    for sel in ["div.profile-summary__text", "[class*='profile-summary__body']",
                "[class*='profile-about']", "[class*='field-name-body']", "[class*='company-about']"]:
        tag = soup.select_one(sel)
        if tag:
            paras = tag.find_all("p")
            text = " ".join(p.get_text(strip=True) for p in paras) if paras else tag.get_text(strip=True)
            if len(text) > 20: return text
    for h in soup.find_all(["h2", "h3", "h4"]):
        if "about" in h.get_text(strip=True).lower():
            s = h.find_next_sibling("p")
            if s and len(s.get_text(strip=True)) > 20: return s.get_text(strip=True)
    meta = soup.find("meta", attrs={"name": "description"})
    return meta["content"].strip() if meta and meta.get("content") else ""

def _rating(soup):
    for a in ["data-rating", "data-score", "aria-label"]:
        for t in soup.select("[class*='sg-rating']"):
            m = re.search(r'(\d+\.?\d*)', t.get(a, ""))
            if m: return m.group(1)
    for sel in ["[class*='rating__number']", "[class*='sg-rating__number']", "[class*='reviews-summary__rating']"]:
        t = soup.select_one(sel)
        if t:
            m = re.search(r'(\d+\.?\d*)', t.get_text(strip=True))
            if m: return m.group(1)
    for t in soup.select("[class*='scroll-to-review']"):
        m = re.search(r'(\d+\.?\d*)', t.get_text(strip=True))
        if m: return m.group(1)
    return ""

def _summary(soup):
    f = {"company_size": "", "project_min_cost": "", "hourly_rate": "", "year_founded": ""}
    for li in soup.select("li.profile-summary__detail"):
        le = li.select_one("span.profile-summary__detail-label")
        if not le: continue
        lt = le.get_text(strip=True).lower()
        ve = li.select_one("span.profile-summary__detail-title") or li.select_one("div.profile-summary__wrapper")
        if not ve: continue
        v = ve.get_text(strip=True)
        if not v: continue
        if "min" in lt and "project" in lt: f["project_min_cost"] = v
        elif "employee" in lt or ("size" in lt and "project" not in lt): f["company_size"] = v
        elif "hourly" in lt or "rate" in lt: f["hourly_rate"] = v
        elif "founded" in lt or "year" in lt:
            m = re.search(r'(\d{4})', v)
            f["year_founded"] = m.group(1) if m else v
    return f

def _locs(soup):
    r = []
    for h in soup.find_all("h2"):
        ht = h.get_text(strip=True)
        if re.match(r'^\d+\s+Location', ht):
            sib = h.find_next_sibling()
            if sib:
                children = sib.select("li, div, span, a")
                for c in children:
                    x = c.get_text(strip=True)
                    if x and "," in x and len(x) < 80 and x not in r:
                        r.append(x)
                if not r:
                    for line in sib.get_text("\n").split("\n"):
                        x = line.strip()
                        if x and "," in x and len(x) < 80 and x not in r:
                            r.append(x)
            if r:
                return r
    for li in soup.select("li.profile-summary__detail"):
        le = li.select_one("span.profile-summary__detail-label")
        if not le:
            continue
        if "location" in le.get_text(strip=True).lower():
            ve = (li.select_one("span.profile-summary__detail-title")
                  or li.select_one("div.profile-summary__wrapper"))
            if ve:
                x = ve.get_text(strip=True)
                if x and x not in r:
                    r.append(x)
    if r:
        return r
    for btn in soup.select("button.location-button"):
        x = btn.get_text(strip=True)
        if x and x.lower() != "headquarters" and x not in r:
            r.append(x)
    if r:
        return r
    for addr in soup.select("address.detailed-address"):
        x = addr.get_text(strip=True)
        if x and x not in r:
            r.append(x)
    return r


def parse_profile(html, cj, src):
    soup = BeautifulSoup(html, "html.parser")
    d = {
        "company_name": src.get("company_name", ""),
        "company_url": src.get("company_url", ""),
        "company_website": src.get("company_website", ""),
        "source_category": src.get("source_category", ""),
        "services": [], "industry": [], "client_type": [], "focus_area": [],
        "locations": [], "company_size": "", "description": "",
        "project_min_cost": "", "clutch_rating": "", "hourly_rate": "",
        "year_founded": "", "languages_services": [], "timezones_services": [],
    }
    n = soup.select_one("h1.profile-header__title")
    if n:
        s = n.find("small")
        if s: s.decompose()
        d["company_name"] = n.get_text(strip=True)
    d["clutch_rating"] = _rating(soup)
    d["description"] = _find_desc(soup)
    sm = _summary(soup)
    d["company_size"] = sm["company_size"]
    d["project_min_cost"] = sm["project_min_cost"]
    d["hourly_rate"] = sm["hourly_rate"]
    d["year_founded"] = sm["year_founded"]
    ch = _map_charts(_parse_chart_data(cj))
    if not ch["services"] and not ch["industry"]:
        ch = _charts_from_legends(soup)
    d["services"] = ch["services"]; d["industry"] = ch["industry"]
    d["client_type"] = ch["client_type"]; d["focus_area"] = ch["focus_area"]
    d["locations"] = _locs(soup)
    for h in soup.find_all(["h2","h3","h4","h5","dt","strong"]):
        if "language" in h.get_text(strip=True).lower():
            p = h.parent
            for _ in range(3):
                items = p.select("li")
                if items:
                    d["languages_services"] = [i.get_text(strip=True) for i in items if i.get_text(strip=True)]
                    break
                p = p.parent
                if p is None: break
            break
    for h in soup.find_all(["h2","h3","h4","h5","dt","strong"]):
        ht = h.get_text(strip=True).lower()
        if "timezone" in ht or "time zone" in ht:
            p = h.parent
            for _ in range(3):
                items = p.select("dd, li, span")
                if items:
                    d["timezones_services"] = [i.get_text(strip=True) for i in items if i.get_text(strip=True)]
                    break
                p = p.parent
                if p is None: break
            break
    return d


async def _block(route):
    if route.request.resource_type in BLOCKED_RESOURCES:
        await route.abort()
    else:
        await route.continue_()


async def fetch_one(browser, sem, idx, co, res, total, ctr):
    url = co.get("company_url", "")
    name = co.get("company_name", "Unknown")
    if not url:
        ctr[0] += 1
        print(f"  [{ctr[0]}/{total}] {name} — skipped")
        res[idx] = co
        return
    async with sem:
        ctx = None
        try:
            ctx = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1440, "height": 900},
                locale="en-US", timezone_id="America/New_York",
            )
            await ctx.add_init_script(STEALTH_JS)
            page = await ctx.new_page()
            await page.route("**/*", _block)
            await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
            try:
                await page.wait_for_selector("h1.profile-header__title", timeout=SELECTOR_TIMEOUT)
            except PWTimeout:
                pass
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(SCROLL_WAIT)
            html = await page.content()
            cj = None
            try: cj = await page.evaluate("window.chartPie || null")
            except: pass
            if html:
                pr = parse_profile(html, cj, co)
                res[idx] = pr
                filled = sum(1 for k, v in pr.items() if v and k not in ("company_url","company_website","source_category"))
                ctr[0] += 1
                print(f"  [{ctr[0]}/{total}] {name} — {filled}/14 fields")
            else:
                ctr[0] += 1
                print(f"  [{ctr[0]}/{total}] {name} — empty")
                res[idx] = co
        except PWTimeout:
            ctr[0] += 1
            print(f"  [{ctr[0]}/{total}] {name} — TIMEOUT")
            res[idx] = co
        except Exception as e:
            ctr[0] += 1
            print(f"  [{ctr[0]}/{total}] {name} — {type(e).__name__}")
            res[idx] = co
        finally:
            if ctx:
                try: await ctx.close()
                except: pass


async def run_stage2(companies):
    total = len(companies)
    print(f"  Concurrency {CONCURRENCY}, resource blocking ON, scroll 0.3s\n")

    if platform.system() != "Windows":
        try: subprocess.run(["pkill", "-9", "-f", "chromium"], timeout=5, capture_output=True)
        except: pass

    await asyncio.sleep(1)
    sem = asyncio.Semaphore(CONCURRENCY)
    res = {}
    ctr = [0]
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=BROWSER_ARGS)
        tasks = [fetch_one(browser, sem, i, c, res, total, ctr) for i, c in enumerate(companies)]
        await asyncio.gather(*tasks)
        try: await browser.close()
        except: pass
    return [res[i] if i in res else companies[i] for i in range(total)]


print(f"Enriching {len(extracted_companies)} companies...\n")
loop = asyncio.get_event_loop()
enriched_companies = loop.run_until_complete(run_stage2(extracted_companies))
print(f"\nDONE — {len(enriched_companies)} profiles enriched")


failed = []
failed_idx = []
for i, c in enumerate(enriched_companies):
    filled = sum(1 for k, v in c.items() if v and k not in ("company_url","company_website","source_category"))
    if filled < 5:
        failed.append(c)
        failed_idx.append(i)

if failed:
    print(f"\nRetrying {len(failed)} failed companies...\n")
    retried = loop.run_until_complete(run_stage2(failed))
    for j, idx in enumerate(failed_idx):
        enriched_companies[idx] = retried[j]
    print(f"Retry done — patched {len(failed)} companies")
else:
    print("\nNo failed companies — all good!")

import re
TECH_KEYWORDS = [
    "software development", "custom software", "web development",
    "mobile app development", "mobile development", "app development",
    "application development", "cloud", "ai ", "artificial intelligence",
    "machine learning", "data science", "data analytics", "data engineering",
    "cybersecurity", "it services", "it consulting", "it management",
    "devops", "qa ", "quality assurance", "saas",
    "platform development", "api development", "blockchain", "iot",
    "embedded", "firmware", "erp", "crm development", "enterprise software",
    "systems integration", "it security", "network security",
    "database", "big data", "business intelligence", "automation",
    "robotic process automation", "ar/vr", "game development",
    "ecommerce development", "e-commerce development",
    "localization", "full stack", "fullstack",
    "backend", "back-end", "frontend", "front-end", "flutter",
    "react", "angular", "node", "python", "java", "php", ".net",
    "ios development", "android development", "cross-platform",
    "progressive web", "wordpress development", "shopify development",
    "magento", "woocommerce", "drupal", "cms development",
    "software engineering", "digital transformation",
    "cloud migration", "aws", "azure", "gcp", "kubernetes", "docker",
    "microservices", "ci/cd", "agile development", "scrum",
    "product development", "mvp development", "prototype",
    "software outsourcing", "offshore development", "nearshore",
    "dedicated team", "staff augmentation",
]

NON_TECH_ONLY = [
    "accounting firm", "law firm", "legal services", "real estate agency",
    "construction company", "insurance brokerage", "tax preparation",
    "architecture firm", "interior design firm", "event planning",
    "print shop", "traditional advertising", "janitorial",
    "landscaping", "plumbing", "electrical contractor",
]

def _norm(text):
    if not text:
        return ""
    if isinstance(text, list):
        parts = []
        for item in text:
            if isinstance(item, dict):
                parts.append(item.get("name", ""))
            else:
                parts.append(str(item))
        text = " ".join(parts)
    return re.sub(r"\s+", " ", str(text).lower()).strip()


def _has_any(text, keywords):
    for kw in keywords:
        if kw in text:
            return True
    return False


def _is_tech_service(name):
    n = name.lower().strip()
    return any(kw in n for kw in TECH_KEYWORDS)


def _calc_tech_split(services):
    if not services or not isinstance(services, list):
        return 0, 0, 0

    tech_sum = 0
    non_tech_sum = 0
    has_pct = False

    for svc in services:
        if not isinstance(svc, dict):
            continue
        name = svc.get("name", "")
        pct_str = svc.get("pct", "")

        pct_val = 0
        if pct_str:
            m = re.search(r"(\d+)", str(pct_str))
            if m:
                pct_val = int(m.group(1))
                has_pct = True

        if _is_tech_service(name):
            tech_sum += pct_val
        else:
            non_tech_sum += pct_val

    if has_pct and (tech_sum + non_tech_sum) > 0:
        total = tech_sum + non_tech_sum
        return round((tech_sum / total) * 100), round((non_tech_sum / total) * 100), len(services)

    tech_count = sum(1 for s in services if isinstance(s, dict) and _is_tech_service(s.get("name", "")))
    total = len([s for s in services if isinstance(s, dict)])
    if total > 0:
        t_pct = round((tech_count / total) * 100)
        return t_pct, 100 - t_pct, total

    return 0, 0, 0

def classify_company(company):
    services = company.get("services", [])
    desc = _norm(company.get("description", ""))
    ind_text = _norm(company.get("industry", []))
    focus = _norm(company.get("focus_area", []))
    client = _norm(company.get("client_type", []))
    all_text = f"{_norm(services)} {ind_text} {desc} {focus}"

    if client:
        b2c_only = ("consumer" in client) and not any(
            kw in client for kw in ["business", "enterprise", "midmarket", "small business", "b2b"]
        )
        if b2c_only:
            return {"bucket": "yellow", "reason": "B2C-only company", "is_b2b": False, "tech_pct": 0, "non_tech_pct": 0}

    tech_pct, non_tech_pct, svc_count = _calc_tech_split(services)

    if svc_count > 0:
        if tech_pct > non_tech_pct:
            return {"bucket": "green", "reason": f"Tech {tech_pct}% > Non-tech {non_tech_pct}%", "is_b2b": True, "tech_pct": tech_pct, "non_tech_pct": non_tech_pct}
        elif tech_pct == non_tech_pct and tech_pct > 0:
            return {"bucket": "red", "reason": f"Tech {tech_pct}% = Non-tech {non_tech_pct}% (tied)", "is_b2b": True, "tech_pct": tech_pct, "non_tech_pct": non_tech_pct}
        elif tech_pct > 0:

            return {"bucket": "yellow", "reason": f"Non-tech dominant: Tech {tech_pct}% < Non-tech {non_tech_pct}%", "is_b2b": True, "tech_pct": tech_pct, "non_tech_pct": non_tech_pct}
        else:
            return {"bucket": "yellow", "reason": "No tech services found", "is_b2b": True, "tech_pct": 0, "non_tech_pct": non_tech_pct}

    has_tech = _has_any(all_text, TECH_KEYWORDS)
    has_hard_non_tech = _has_any(all_text, NON_TECH_ONLY)

    if has_tech and not has_hard_non_tech:
        return {"bucket": "red", "reason": "Tech in description but no services data", "is_b2b": True, "tech_pct": -1, "non_tech_pct": -1}

    if has_hard_non_tech and not has_tech:
        return {"bucket": "yellow", "reason": "Non-tech company", "is_b2b": True, "tech_pct": 0, "non_tech_pct": 0}

    return {"bucket": "red", "reason": "Insufficient data", "is_b2b": True, "tech_pct": -1, "non_tech_pct": -1}

def filter_enriched(companies, keep_buckets=("green",)):
    passed, rejected = [], []
    stats = {"green": 0, "red": 0, "yellow": 0}

    for co in companies:
        result = classify_company(co)
        co["icp_bucket"] = result["bucket"]
        co["icp_reason"] = result["reason"]
        co["is_b2b"] = result["is_b2b"]
        co["tech_pct"] = result["tech_pct"]
        co["non_tech_pct"] = result["non_tech_pct"]
        stats[result["bucket"]] += 1

        if result["bucket"] in keep_buckets:
            passed.append(co)
        else:
            rejected.append(co)

    return passed, rejected, stats

if __name__ == "__main__" or "enriched_companies" in dir():
    passed, rejected, stats = filter_enriched(enriched_companies, keep_buckets=("green",))

    print(f"\n{'=' * 55}")
    print(f"  ICP FILTER RESULTS (tech > non-tech = pass)")
    print(f"{'=' * 55}")
    print(f"  Total companies : {len(enriched_companies)}")
    print(f"  Green (tech > non-tech) : {stats['green']}")
    print(f"  Red (review)            : {stats['red']}")
    print(f"  Yellow (fail)           : {stats['yellow']}")
    print(f"  Kept                    : {len(passed)}")
    print(f"{'=' * 55}")

    if rejected:
        print(f"\n  Sample rejected:")
        for c in rejected[:10]:
            t = c.get("tech_pct", "?")
            nt = c.get("non_tech_pct", "?")
            print(f"    {c.get('company_name', '?'):40s}  [{c['icp_bucket']}] tech {t}% / non-tech {nt}% — {c['icp_reason']}")

    if passed:
        print(f"\n  Sample passed:")
        for c in passed[:5]:
            print(f"    {c.get('company_name', '?'):40s}  tech {c.get('tech_pct', '?')}% / non-tech {c.get('non_tech_pct', '?')}%")

    filtered_companies = passed
    print(f"\n  filtered_companies now has {len(filtered_companies)} leads.")

import re
import csv
import html as html_mod

OUTPUT_FILE = "clutch_enriched_leads.csv"

def clean_text(val):
    if not isinstance(val, str):
        return val
    val = re.sub(r'<[^>]+>', ' ', val)
    val = html_mod.unescape(val)
    val = val.replace('\u2018', "'").replace('\u2019', "'")
    val = val.replace('\u201C', '"').replace('\u201D', '"')
    val = val.replace('\u2013', '-').replace('\u2014', '-')
    val = val.replace('\u2026', '...')
    val = val.replace('\u00A0', ' ')
    return re.sub(r'\s+', ' ', val).strip()

def flatten_items(items):
    if not items:
        return ""
    if isinstance(items[0], dict) and "name" in items[0]:
        parts = []
        for item in items:
            name = item.get("name", "")
            pct = item.get("pct", "")
            parts.append(f"{name} ({pct})" if pct else name)
        return "; ".join(parts)
    return "; ".join(str(i) for i in items)

def flatten_focus(focus_list):
    if not focus_list:
        return ""
    if isinstance(focus_list[0], dict) and "category" in focus_list[0]:
        sections = []
        for group in focus_list:
            cat = group.get("category", "")
            items = flatten_items(group.get("items", []))
            sections.append(f"[{cat}] {items}")
        return " | ".join(sections)
    return flatten_items(focus_list)

COLUMNS = [
    "company_name", "company_url", "company_website", "source_category",
    "clutch_rating", "project_min_cost", "hourly_rate", "company_size",
    "year_founded", "description", "services", "industry",
    "client_type", "focus_area", "locations", "languages_services",
    "timezones_services",
]

rows = []
for company in filtered_companies:
    row = []
    for col in COLUMNS:
        val = company.get(col, "")
        if col == "focus_area":
            row.append(clean_text(flatten_focus(val)))
        elif col in ("services", "industry", "client_type"):
            row.append(clean_text(flatten_items(val)))
        elif col in ("locations", "languages_services", "timezones_services"):
            row.append(clean_text("; ".join(val) if isinstance(val, list) else str(val)))
        else:
            row.append(clean_text(val if val else ""))
    rows.append(row)

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(COLUMNS)
    writer.writerows(rows)

print(f"Saved {len(rows)} green leads to {OUTPUT_FILE}")

