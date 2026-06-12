import requests
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import urljoin, urlparse

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_RE = re.compile(r"(\+?[\d][\d\s\-().]{6,}\d)")


def scrape_url(url: str) -> dict:
    """
    Step 2 — Smart Web Fetch Module
    1. Fetches the main page
    2. If no contacts found, automatically looks for a Contact/About page
    3. If still empty, falls back to Selenium
    Combines results from all pages.
    """
    result = {
        "url": url, "title": None, "name": None,
        "description": None, "emails": [], "phones": [],
        "social_links": [], "error": None, "pages_scanned": []
    }

    # ── Try main page first ──────────────────────────────────────────────────
    main = _fetch_static(url)
    if main.get("error"):
        result["error"] = main["error"] + " (This site may block automated access.)"
        return result

    result.update(main)
    result["pages_scanned"] = [url]

    all_emails = set(main["emails"])
    all_phones = set(main["phones"])
    all_social = set(main["social_links"])

    # ── If few contacts, hunt for contact/about pages ────────────────────────
    if len(all_emails) < 2:
        contact_links = _find_contact_links(url)
        for link in contact_links[:3]:   # scan up to 3 contact pages
            try:
                sub = _fetch_static(link)
                if not sub.get("error"):
                    all_emails.update(sub["emails"])
                    all_phones.update(sub["phones"])
                    all_social.update(sub["social_links"])
                    result["pages_scanned"].append(link)
                    if not result.get("description") and sub.get("description"):
                        result["description"] = sub["description"]
                time.sleep(0.5)
            except Exception:
                pass

    # Note: Selenium fallback available via scrape_with_selenium() but disabled
    # by default to keep responses fast and reliable.

    result["emails"] = list(all_emails)[:15]
    result["phones"] = list(all_phones)[:15]
    result["social_links"] = list(all_social)[:10]
    return result


def _find_contact_links(base_url: str) -> list:
    """Find links to contact/about pages on the main page."""
    links = []
    try:
        resp = requests.get(base_url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(resp.text, "html.parser")
        keywords = ["contact", "about", "اتصل", "تواصل", "من نحن", "reach", "support", "get-in-touch"]
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            text = a.get_text(strip=True).lower()
            if any(kw in href or kw in text for kw in keywords):
                full = urljoin(base_url, a["href"])
                if full not in links and urlparse(full).netloc == urlparse(base_url).netloc:
                    links.append(full)
    except Exception as e:
        print(f"[scraper] contact-link search error: {e}")
    return links


def _fetch_static(url: str) -> dict:
    """Fetch one page statically and parse it."""
    result = {
        "url": url, "title": None, "name": None, "description": None,
        "emails": [], "phones": [], "social_links": [], "error": None
    }
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        result["error"] = "Could not connect."
        return result
    except requests.exceptions.Timeout:
        result["error"] = "Timeout."
        return result
    except Exception as e:
        result["error"] = str(e)
        return result

    return _parse_html(resp.text, url)


def scrape_with_selenium(url: str) -> dict:
    """Selenium fallback for JavaScript-rendered pages."""
    result = {
        "url": url, "title": None, "name": None, "description": None,
        "emails": [], "phones": [], "social_links": [], "error": None,
        "pages_scanned": [url]
    }
    try:
        from selenium import webdriver
        from selenium.webdriver.edge.service import Service
        from selenium.webdriver.edge.options import Options
        from webdriver_manager.microsoft import EdgeChromiumDriverManager

        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(f"user-agent={HEADERS['User-Agent']}")

        print(f"[Selenium] Starting Edge for: {url}")
        service = Service(EdgeChromiumDriverManager().install())
        driver  = webdriver.Edge(service=service, options=options)
        driver.get(url)
        time.sleep(4)
        html  = driver.page_source
        title = driver.title
        driver.quit()

        parsed = _parse_html(html, url)
        parsed["title"] = title or parsed["title"]
        parsed["name"]  = title or parsed["name"]
        parsed["pages_scanned"] = [url]
        return parsed
    except Exception as e:
        print(f"[Selenium] Error: {e}")
        result["error"] = f"Could not extract: {str(e)[:80]}"
        return result


def _parse_html(html: str, url: str) -> dict:
    """Parse HTML and extract all contact info with smart phone filtering."""
    result = {
        "url": url, "title": None, "name": None, "description": None,
        "emails": [], "phones": [], "social_links": [], "error": None
    }
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    full_text = soup.get_text(separator=" ", strip=True)

    title_tag = soup.find("title")
    result["title"] = title_tag.get_text(strip=True) if title_tag else url

    meta = soup.find("meta", attrs={"name": "description"}) or \
           soup.find("meta", attrs={"property": "og:description"})
    if meta and meta.get("content"):
        result["description"] = meta["content"][:300]

    og_name = soup.find("meta", property="og:site_name")
    if og_name and og_name.get("content"):
        result["name"] = og_name["content"]
    else:
        h1 = soup.find("h1")
        result["name"] = h1.get_text(strip=True) if h1 else result["title"]

    # Emails — also check mailto: links
    emails = set(EMAIL_RE.findall(full_text))
    for a in soup.find_all("a", href=True):
        if a["href"].lower().startswith("mailto:"):
            em = a["href"][7:].split("?")[0].strip()
            if EMAIL_RE.match(em):
                emails.add(em)
    result["emails"] = [e for e in emails if not any(
        x in e.lower() for x in ["example.com", "yourdomain", "test@", "email@", ".png", ".jpg"]
    )][:15]

    # Phones — also check tel: links + smart filter
    phones = set()
    for a in soup.find_all("a", href=True):
        if a["href"].lower().startswith("tel:"):
            phones.add(a["href"][4:].strip())
    raw = PHONE_RE.findall(full_text)
    for p in raw:
        p = p.strip()
        digits = re.sub(r"\D", "", p)

        # ── Date / year filters ──
        if re.search(r"(19|20)\d{2}\s*[-/]\s*(19|20)\d{2}", p):
            continue
        if re.search(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", p):
            continue
        if re.search(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{4}", p):
            continue
        if re.match(r"^(19|20)\d{2}[\s-]+\d{1,2}$", p):
            continue

        # ── Accept only real phone formats ──
        is_valid = (
            8 <= len(digits) <= 15 and
            len(set(digits)) > 3 and
            (p.startswith("+") or p.startswith("00") or
             p.startswith("(") or
             (p.startswith("0") and len(digits) >= 9))
        )
        if is_valid:
            phones.add(p)
    result["phones"] = list(phones)[:15]

    # Social links
    social_domains = ["linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com", "wa.me", "whatsapp"]
    social = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(d in href.lower() for d in social_domains) and href not in social:
            social.append(href)
    result["social_links"] = social[:10]

    return result