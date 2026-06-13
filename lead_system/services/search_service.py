import requests
import re
import time
import urllib.parse
from bs4 import BeautifulSoup

# ── All API keys are loaded from config.py (edit keys there, not here) ─────────
import os
# Default placeholders
SERP_API_KEYS = ["YOUR_API_KEY_HERE"]
SERPER_API_KEY = "YOUR_SERPER_KEY_HERE"
GOOGLE_PLACES_KEY = "YOUR_GOOGLE_PLACES_KEY_HERE"
# Load config.py directly by its file path (works no matter where Python runs)
try:
    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _config_path = os.path.join(_ROOT, "config.py")
    _cfg = {}
    with open(_config_path, "r", encoding="utf-8") as _f:
        exec(_f.read(), _cfg)
    SERP_API_KEYS = _cfg.get("SERP_API_KEYS", SERP_API_KEYS)
    SERPER_API_KEY = _cfg.get("SERPER_API_KEY", SERPER_API_KEY)
    GOOGLE_PLACES_KEY = _cfg.get("GOOGLE_PLACES_KEY", GOOGLE_PLACES_KEY)
    print(f"[config] Loaded keys — SerpAPI:{len([k for k in SERP_API_KEYS if k!='YOUR_API_KEY_HERE'])} Serper:{'YES' if SERPER_API_KEY and SERPER_API_KEY!='YOUR_SERPER_KEY_HERE' else 'NO'} Places:{'YES' if GOOGLE_PLACES_KEY and GOOGLE_PLACES_KEY!='YOUR_GOOGLE_PLACES_KEY_HERE' else 'NO'}")
except Exception as e:
    print(f"[config] FAILED to load config.py: {e}")
SERP_API_KEY = SERP_API_KEYS[0] if SERP_API_KEYS else "YOUR_API_KEY_HERE"
# ─────────────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_RE = re.compile(r"(\+?[\d][\d\s\-().]{6,}\d)")

INTEREST_KEYWORDS = {
    "phones":        ["phone", "mobile", "smartphone", "iphone", "samsung", "huawei"],
    "laptops":       ["laptop", "notebook", "macbook", "dell", "hp", "lenovo"],
    "electronics":   ["electronics", "gadget", "device", "tech"],
    "smart_devices": ["smart", "iot", "smartwatch", "alexa", "wearable", "tablet"],
    "clothes":       ["fashion", "clothing", "apparel", "wear", "dress", "boutique"],
    "real_estate":   ["real estate", "property", "apartment", "villa", "rent", "sale", "construction", "building", "mortgage"],
    "food_beverage": ["restaurant", "cafe", "food", "beverage", "catering", "bakery", "coffee", "kitchen", "dining"],
    "automotive":    ["car", "vehicle", "auto", "motor", "garage", "dealership", "toyota", "bmw", "mercedes", "spare parts"],
    "healthcare":    ["clinic", "hospital", "doctor", "medical", "pharmacy", "health", "dental", "laboratory", "nurse"],
    "beauty":        ["beauty", "salon", "spa", "cosmetics", "makeup", "skincare", "barber", "nail", "hair"],
    "education":     ["school", "university", "training", "academy", "institute", "tutor", "course", "college", "e-learning"],
    "finance":       ["bank", "insurance", "financial", "investment", "accounting", "forex", "loan", "fintech", "trading"],
    "travel":        ["travel", "hotel", "tourism", "tour", "airline", "resort", "booking", "holiday", "visa"],
    "construction":  ["construction", "contractor", "architect", "interior", "design", "furniture", "flooring", "cement"],
    "it_services":   ["software", "web", "developer", "it", "cyber", "hosting", "app", "digital", "saas", "cloud"],
    "retail":        ["store", "shop", "wholesale", "distributor", "supplier", "market", "retail", "ecommerce", "outlet"],
    "marketing":     ["marketing", "advertising", "agency", "branding", "seo", "social media", "campaign", "media"],
    "logistics":     ["shipping", "delivery", "logistics", "freight", "courier", "supply chain", "warehouse", "transport"],
}


def run_search(keywords: list, platform: str, region: str) -> list:
    """
    Step 1 — Research Module
    Searches EACH keyword across all sources IN PARALLEL so total time = slowest source, not sum.
    """
    from concurrent.futures import ThreadPoolExecutor

    def _safe(fn, *args):
        try:
            return fn(*args)
        except Exception as e:
            print(f"[search_service] {fn.__name__} failed: {e}")
            return []

    tasks = []
    for kw in keywords:
        query = kw.strip()
        if not query:
            continue
        print(f"[search_service] === Searching keyword: {query} ===")

        if any(k and k != "YOUR_API_KEY_HERE" for k in SERP_API_KEYS):
            tasks.append((search_serpapi,       query, platform, region, keywords))
        tasks.append((search_serper,            query, platform, region, keywords))
        tasks.append((search_duckduckgo,        query, platform, region, keywords))
        tasks.append((search_bing,              query, platform, region, keywords))
        if platform in ("all", "web", "directories", "marketplace"):
            tasks.append((search_google_places, query, platform, region, keywords))
        if platform in ("all", "web", "directories", "maps"):
            tasks.append((search_serper_maps,   query, platform, region, keywords))
        if platform in ("all", "social", "linkedin"):
            tasks.append((search_linkedin_deep, query, platform, region, keywords))

    results = []
    if tasks:
        from concurrent.futures import wait as cf_wait
        ex = ThreadPoolExecutor(max_workers=min(len(tasks), 8))
        futures = [ex.submit(_safe, fn, *args) for fn, *args in tasks]
        done, _ = cf_wait(futures, timeout=22)
        ex.shutdown(wait=False, cancel_futures=True)
        for f in done:
            try:
                results.extend(f.result())
            except Exception:
                pass

    # Final fallback — demo data only if nothing found at all
    if not results:
        print(f"[search_service] Using demo data")
        results = generate_demo_results(keywords, platform, region)

    # Deduplicate by URL
    seen, unique = set(), []
    for r in results:
        if r["source_url"] not in seen:
            seen.add(r["source_url"])
            unique.append(r)

    # Deep enrich ALL combined results — visit pages to extract missing phones/emails
    # Runs across every source (DDG, Bing, Serper, Maps, LinkedIn, etc.), not just SerpAPI
    unique = enrich_results(unique, keywords, max_enrich=10)

    # Score and sort (highest score first)
    for r in unique:
        r["score"] = compute_score(r, keywords)
    unique.sort(key=lambda x: x["score"], reverse=True)
    return unique[:1000]   # allow up to 1000 results



def search_serpapi(query: str, platform: str, region: str, keywords: list) -> list:
    """Search using SerpAPI — real Google results."""
    region_map = {
        "lebanon": "lb", "mena": "ae", "gcc": "sa",
        "global": "us", "europe": "uk", "us": "us"
    }
    country = region_map.get(region, "us")

    # Major cities to expand geographic coverage (more cities = more results)
    region_cities = {
        "lebanon": ["beirut", "tripoli", "saida", "jounieh", "zahle", "byblos", "tyre", "baalbek", "nabatieh", "aley", "batroun", "jbeil"],
        "mena":    ["dubai", "cairo", "amman", "riyadh", "doha", "abu dhabi", "kuwait", "muscat"],
        "gcc":     ["dubai", "riyadh", "doha", "kuwait", "manama", "abu dhabi", "jeddah", "sharjah"],
        "global":  ["new york", "london", "dubai", "paris", "tokyo", "singapore"],
        "europe":  ["london", "paris", "berlin", "madrid", "rome", "amsterdam"],
        "us":      ["new york", "los angeles", "chicago", "houston", "miami", "boston"],
    }
    cities = region_cities.get(region, [region])

    # Build MANY query variations per platform to maximize result count.
    # Each variation is searched separately and results are combined + deduplicated.
    base_variations = [
        f"{query} contact email phone business",
        f"{query} {region} company contact",
        f"{query} services email phone",
        f"best {query} {region}",
        f"{query} list directory {region}",
    ]
    # Add a per-city variation to widen coverage
    city_variations = [f"{query} {city} contact email" for city in cities]

    platform_queries = {
        "linkedin":  [f"site:linkedin.com {query} {c}" for c in cities] + [f"site:linkedin.com {query} contact email"],
        "facebook":  [f'site:facebook.com {query} {c}' for c in cities] + [f'site:facebook.com {query} (page OR business)'],
        "instagram": [f"site:instagram.com {query} {c}" for c in cities] + [f"site:instagram.com {query} contact"],
        "twitter":   [f"(site:twitter.com OR site:x.com) {query} {c}" for c in cities[:3]],
        "social":    [f"{query} {c} (site:facebook.com OR site:instagram.com OR site:linkedin.com)" for c in cities],
        "marketplace": [f"{query} {c} (site:olx.com.lb OR site:dubizzle.com OR site:amazon.com)" for c in cities] ,
        "directories": [f"{query} {c} (site:yellowpages.com.lb OR site:yelp.com)" for c in cities],
        "maps":      [f"{query} {c} google maps business listing" for c in cities] + [f"{query} {region} business contact maps"],
        "web":       base_variations + city_variations,
        "all":       base_variations + city_variations + [
            f"{query} (site:linkedin.com OR site:facebook.com OR site:instagram.com)",
            f"{query} (site:yellowpages.com.lb OR site:olx.com.lb OR site:yelp.com)",
        ],
    }
    query_variations = platform_queries.get(platform, base_variations)
    # Limit to first 4 variations to avoid rate-limiting (which causes empty results)
    query_variations = query_variations[:4]

    try:
        results = []
        seen_urls = set()
        # Active keys (skip placeholders)
        active_keys = [k for k in SERP_API_KEYS if k and k != "YOUR_API_KEY_HERE"]
        if not active_keys:
            return []
        key_index = 0
        # Loop through each query variation to collect up to 100 unique leads.
        for full_query in query_variations:
            if len(results) >= 300:
                break
            params = {
                "api_key": active_keys[key_index],
                "engine":  "google",
                "q":       full_query,
                "gl":      country,
                "hl":      "en",
                "num":     "100",
            }
            try:
                resp = requests.get("https://serpapi.com/search", params=params, timeout=7)
                data = resp.json()
            except Exception as e:
                print(f"[SerpAPI] request failed: {e}")
                continue   # try next variation

            if "error" in data:
                print(f"[SerpAPI] Error: {data['error']}")
                # If this key is out of quota, switch to the next key
                if key_index < len(active_keys) - 1:
                    key_index += 1
                    print(f"[SerpAPI] Switching to key #{key_index + 1}")
                continue   # try next variation

            page_items = data.get("organic_results", [])
            if not page_items:
                continue   # try next variation

            for item in page_items:
                title   = item.get("title", "")
                url     = item.get("link", "")
                snippet = item.get("snippet", "")

                # Skip duplicates
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                email = extract_email(snippet)
                phone = extract_phone(snippet)

                results.append({
                    "name":       title,
                    "email":      email,
                    "phone":      phone,
                    "source_url": url,
                    "platform":   detect_platform(url),
                    "snippet":    snippet[:200],
                    "interests":  detect_interests(title + " " + snippet, keywords),
                    "score":      0
                })

        results = results[:300]

        print(f"[SerpAPI] Found {len(results)} results")
        return results

    except Exception as e:
        print(f"[SerpAPI] Exception: {e}")
        return []


def search_duckduckgo(query: str, platform: str, region: str, keywords: list) -> list:
    """Fallback: DuckDuckGo HTML search."""
    from bs4 import BeautifulSoup

    region_map = {
        "lebanon": "Lebanon", "mena": "Middle East",
        "gcc": "Gulf", "global": "", "europe": "Europe", "us": "USA"
    }
    loc = region_map.get(region, "")
    platform_map = {
        "linkedin": f"site:linkedin.com {query} {loc}",
        "facebook": f"site:facebook.com {query} {loc} page OR business",
        "instagram":f"site:instagram.com {query} {loc}",
        "twitter":  f"(site:twitter.com OR site:x.com) {query} {loc}",
        "social":   f"{query} {loc} (site:facebook.com OR site:instagram.com OR site:linkedin.com)",
        "marketplace": f"{query} {loc} (site:olx.com.lb OR site:dubizzle.com OR site:amazon.com)",
        "directories": f"{query} {loc} (site:yellowpages.com.lb OR site:yelp.com)",
        "web":      f"{query} {loc} business contact email phone",
        "all":      f"{query} {loc} contact email phone business",
    }
    full_query = platform_map.get(platform, f"{query} {loc} business contact")

    results = []
    try:
        # DuckDuckGo paginates via 's' parameter (0, 30, 60...)
        for offset in range(0, 150, 30):
            encoded = urllib.parse.quote(full_query)
            url     = f"https://html.duckduckgo.com/html/?q={encoded}&s={offset}"
            resp = requests.get(url, headers=HEADERS, timeout=7)
            if resp.status_code != 200:
                break
            soup = BeautifulSoup(resp.text, "html.parser")
            blocks = soup.select(".result__body")
            if not blocks:
                break
            for result in blocks:
                title_el   = result.select_one(".result__title a")
                snippet_el = result.select_one(".result__snippet")
                if not title_el:
                    continue
                title   = title_el.get_text(strip=True)
                href    = title_el.get("href", "")
                if "uddg=" in href:
                    href = urllib.parse.unquote(href.split("uddg=")[-1].split("&")[0])
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                results.append({
                    "name":       title,
                    "email":      extract_email(snippet),
                    "phone":      extract_phone(snippet),
                    "source_url": href,
                    "platform":   detect_platform(href),
                    "snippet":    snippet[:200],
                    "interests":  detect_interests(title + " " + snippet, keywords),
                    "score":      0
                })
            time.sleep(1)
    except Exception as e:
        print(f"[DDG] Error: {e}")
    print(f"[DDG] Found {len(results)} results")
    return results


def search_serper(query, platform, region, keywords):
    """Serper.dev — real Google results API (free 2,500/month). Independent of SerpAPI."""
    if not SERPER_API_KEY or SERPER_API_KEY == "YOUR_SERPER_KEY_HERE":
        return []

    loc_map = {"lebanon":"Lebanon","mena":"United Arab Emirates","gcc":"Saudi Arabia",
               "global":"","europe":"United Kingdom","us":"United States"}
    loc = loc_map.get(region, "")

    # Free Serper accounts don't allow "site:" operator — use platform name as a keyword instead
    platform_keyword = {
        "linkedin":  "linkedin",
        "facebook":  "facebook",
        "instagram": "instagram",
        "twitter":   "twitter",
        "social":    "facebook instagram linkedin",
        "marketplace": "olx dubizzle amazon",
        "directories": "yellowpages yelp directory",
    }
    extra = platform_keyword.get(platform, "")

    # Cities to expand a single keyword across (more cities = more results)
    region_cities = {
        "lebanon": ["Lebanon", "Beirut", "Tripoli", "Saida", "Jounieh", "Zahle", "Byblos"],
        "mena":    ["UAE", "Dubai", "Cairo", "Amman", "Riyadh"],
        "gcc":     ["Dubai", "Riyadh", "Doha", "Kuwait", "Abu Dhabi"],
        "global":  ["", "USA", "UK", "Dubai"],
        "europe":  ["UK", "London", "Paris", "Berlin"],
        "us":      ["USA", "New York", "Los Angeles", "Chicago"],
    }
    cities = region_cities.get(region, [loc])

    # Build several query variations for the SINGLE keyword
    variations = []
    for city in cities:
        variations.append(f"{query} {extra} {city} contact email phone".strip())
    variations.append(f"best {query} {extra} {loc}".strip())
    variations.append(f"{query} {extra} {loc} directory list".strip())

    results = []
    seen = set()
    try:
        for vquery in variations:
            if len(results) >= 300:
                break
            # 2 pages per variation
            for page in range(1, 3):
                resp = requests.post(
                    "https://google.serper.dev/search",
                    headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                    json={"q": vquery, "num": 100, "page": page},
                    timeout=7
                )
                if resp.status_code != 200:
                    print(f"[Serper] HTTP {resp.status_code}: {resp.text[:120]}")
                    break
                data = resp.json()
                organic = data.get("organic", [])
                if not organic:
                    break
                for item in organic:
                    title   = item.get("title", "")
                    url     = item.get("link", "")
                    snippet = item.get("snippet", "")
                    if url in seen:
                        continue
                    seen.add(url)
                    results.append({
                        "name": title,
                        "email": extract_email(snippet),
                        "phone": extract_phone(snippet),
                        "source_url": url,
                        "platform": detect_platform(url),
                        "snippet": snippet[:200],
                        "interests": detect_interests(title + " " + snippet, keywords),
                        "score": 0
                    })
    except Exception as e:
        print(f"[Serper] Error: {e}")
    print(f"[Serper] Found {len(results)} results")
    return results


def search_bing(query, platform, region, keywords):
    """Free Bing search scraping — adds more results to increase coverage."""
    loc_map = {"lebanon":"Lebanon","mena":"UAE","gcc":"Saudi Arabia","global":"","europe":"UK","us":"USA"}
    loc = loc_map.get(region, "")

    region_cities = {
        "lebanon": ["Beirut", "Tripoli", "Saida", "Jounieh", "Zahle"],
        "mena":    ["Dubai", "Cairo", "Amman"],
        "gcc":     ["Dubai", "Riyadh", "Doha"],
    }
    cities = region_cities.get(region, [loc])

    # For social platforms, use keyword (site: returns too few from Bing)
    platform_keyword = {
        "linkedin":  "linkedin",
        "facebook":  "facebook",
        "instagram": "instagram",
        "twitter":   "twitter",
        "social":    "facebook instagram linkedin",
        "marketplace": "olx dubizzle amazon",
        "directories": "yellowpages yelp",
    }
    pfx = platform_keyword.get(platform, "")

    queries = [f"{query} {pfx} {loc} contact email phone"]
    queries += [f"{query} {pfx} {c} contact email" for c in cities[:3]]   # limit cities

    results = []
    seen = set()
    for q in queries:
        if len(results) >= 300:
            break
        try:
            for first in [1, 11, 21, 31, 41]:   # Bing pagination
                encoded = urllib.parse.quote(q)
                url = f"https://www.bing.com/search?q={encoded}&first={first}"
                resp = requests.get(url, headers=HEADERS, timeout=7)
                if resp.status_code != 200:
                    break
                soup = BeautifulSoup(resp.text, "html.parser")
                blocks = soup.select("li.b_algo")
                if not blocks:
                    break
                for b in blocks:
                    h2 = b.find("h2")
                    link_el = h2.find("a") if h2 else None
                    if not link_el:
                        continue
                    title = link_el.get_text(strip=True)
                    href = link_el.get("href", "")

                    # Bing wraps real URLs in a redirect (bing.com/ck/a?...&u=...).
                    # Try to find the real URL shown in the citation cite tag instead.
                    cite = b.find("cite")
                    real_url = cite.get_text(strip=True) if cite else ""
                    if real_url:
                        if not real_url.startswith("http"):
                            real_url = "https://" + real_url.split(" ")[0]
                        href = real_url.split(" ")[0]

                    # Skip if still a bing redirect
                    if "bing.com/ck/" in href:
                        continue
                    if not href or href in seen:
                        continue
                    seen.add(href)
                    p = b.find("p")
                    snippet = p.get_text(strip=True) if p else ""
                    results.append({
                        "name": title,
                        "email": extract_email(snippet),
                        "phone": extract_phone(snippet),
                        "source_url": href,
                        "platform": detect_platform(href),
                        "snippet": snippet[:200],
                        "interests": detect_interests(title + " " + snippet, keywords),
                        "score": 0
                    })
                time.sleep(0.6)
        except Exception as e:
            print(f"[Bing] Error: {e}")
            continue
    print(f"[Bing] Found {len(results)} results")
    return results

def _scrape_directory(base_url, query, region, keywords, source_name):
    """Generic directory scraper for business listing sites."""
    loc_map = {"lebanon":"Lebanon","mena":"UAE","gcc":"Saudi Arabia","global":"","europe":"UK","us":"USA"}
    loc = loc_map.get(region, "")
    results = []
    try:
        # Search the directory via a general engine query targeting that site
        q = f"{query} {loc} {source_name}"
        encoded = urllib.parse.quote(q)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        resp = requests.get(url, headers=HEADERS, timeout=7)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for r in soup.select(".result__body"):
                t = r.select_one(".result__title a")
                s = r.select_one(".result__snippet")
                if not t:
                    continue
                title = t.get_text(strip=True)
                href = t.get("href", "")
                if "uddg=" in href:
                    href = urllib.parse.unquote(href.split("uddg=")[-1].split("&")[0])
                snippet = s.get_text(strip=True) if s else ""
                results.append({
                    "name": title,
                    "email": extract_email(snippet),
                    "phone": extract_phone(snippet),
                    "source_url": href,
                    "platform": detect_platform(href),
                    "snippet": snippet[:200],
                    "interests": detect_interests(title + " " + snippet, keywords),
                    "score": 0
                })
    except Exception as e:
        print(f"[{source_name}] Error: {e}")
    print(f"[{source_name}] Found {len(results)} results")
    return results


def search_google_places(query, platform, region, keywords):
    """
    Google Places API — real businesses with names, addresses, and phone numbers.
    Legal & official (businesses publish this data publicly).
    Free up to $200/month credit.
    """
    if not GOOGLE_PLACES_KEY or GOOGLE_PLACES_KEY == "YOUR_GOOGLE_PLACES_KEY_HERE":
        return []

    loc_map = {"lebanon":"Lebanon","mena":"UAE","gcc":"Saudi Arabia",
               "global":"","europe":"UK","us":"USA"}
    loc = loc_map.get(region, "")

    region_cities = {
        "lebanon": ["Beirut", "Tripoli", "Saida", "Jounieh", "Zahle"],
        "mena":    ["Dubai", "Cairo", "Amman"],
        "gcc":     ["Dubai", "Riyadh", "Doha"],
    }
    cities = region_cities.get(region, [loc])

    results = []
    seen = set()
    try:
        for city in cities:
            search_text = f"{query} in {city}"
            # Text Search API
            resp = requests.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params={"query": search_text, "key": GOOGLE_PLACES_KEY},
                timeout=7
            )
            data = resp.json()
            if data.get("status") not in ("OK", "ZERO_RESULTS"):
                print(f"[Google Places] {data.get('status')}: {data.get('error_message','')}")
                break

            for place in data.get("results", []):
                pid = place.get("place_id")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                name = place.get("name", "")
                address = place.get("formatted_address", "")

                # Get phone via Place Details
                phone = ""
                try:
                    det = requests.get(
                        "https://maps.googleapis.com/maps/api/place/details/json",
                        params={"place_id": pid, "fields": "formatted_phone_number,website",
                                "key": GOOGLE_PLACES_KEY},
                        timeout=7
                    ).json()
                    phone = det.get("result", {}).get("formatted_phone_number", "")
                    website = det.get("result", {}).get("website", "")
                except Exception:
                    website = ""

                results.append({
                    "name": name,
                    "email": "",
                    "phone": phone,
                    "source_url": website or f"https://www.google.com/maps/place/?q=place_id:{pid}",
                    "platform": "maps",
                    "snippet": address[:200],
                    "interests": detect_interests(name + " " + query, keywords),
                    "score": 0
                })
            time.sleep(0.5)
    except Exception as e:
        print(f"[Google Places] Error: {e}")
    print(f"[Google Places] Found {len(results)} results")
    return results


def search_serper_maps(query, platform, region, keywords):
    """Serper Maps — Google Maps business results via Serper /maps endpoint (no extra API key needed)."""
    if not SERPER_API_KEY or SERPER_API_KEY == "YOUR_SERPER_KEY_HERE":
        return []

    loc_map = {"lebanon":"Lebanon","mena":"UAE","gcc":"Saudi Arabia",
               "global":"","europe":"UK","us":"USA"}
    loc = loc_map.get(region, "")

    region_cities = {
        "lebanon": ["Beirut", "Tripoli", "Saida", "Jounieh", "Zahle"],
        "mena":    ["Dubai", "Cairo", "Amman"],
        "gcc":     ["Dubai", "Riyadh", "Doha"],
        "global":  ["New York", "London", "Dubai"],
        "europe":  ["London", "Paris", "Berlin"],
        "us":      ["New York", "Los Angeles", "Chicago"],
    }
    cities = region_cities.get(region, [loc] if loc else [query])

    results = []
    seen = set()
    try:
        for city in cities:
            search_q = f"{query} {city}".strip()
            resp = requests.post(
                "https://google.serper.dev/maps",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": search_q, "num": 20},
                timeout=7
            )
            if resp.status_code != 200:
                print(f"[Serper Maps] HTTP {resp.status_code}: {resp.text[:80]}")
                break
            data = resp.json()
            for place in data.get("places", []):
                name    = place.get("title", "")
                address = place.get("address", "")
                phone   = place.get("phoneNumber", "") or place.get("phone", "")
                website = place.get("website", "")
                cid     = place.get("cid", "") or place.get("placeId", "")
                url     = website or (f"https://www.google.com/maps/place/?q=place_id:{cid}" if cid else "")
                if not url or url in seen:
                    continue
                seen.add(url)
                results.append({
                    "name":       name,
                    "email":      "",
                    "phone":      phone,
                    "source_url": url,
                    "platform":   "maps",
                    "snippet":    address[:200],
                    "interests":  detect_interests(name + " " + query, keywords),
                    "score":      0
                })
            time.sleep(0.3)
    except Exception as e:
        print(f"[Serper Maps] Error: {e}")
    print(f"[Serper Maps] Found {len(results)} results")
    return results


def search_linkedin_deep(query, platform, region, keywords):
    """Dedicated LinkedIn profile/company search — only returns linkedin.com URLs."""
    loc_map = {"lebanon":"Lebanon","mena":"UAE","gcc":"Saudi Arabia",
               "global":"","europe":"UK","us":"USA"}
    loc = loc_map.get(region, "")

    region_cities = {
        "lebanon": ["Beirut", "Lebanon", "Tripoli", "Jounieh"],
        "mena":    ["UAE", "Dubai", "Cairo", "Amman"],
        "gcc":     ["Dubai", "Riyadh", "Doha"],
        "global":  ["", "USA", "UK"],
        "europe":  ["UK", "London", "Paris"],
        "us":      ["USA", "New York", "Los Angeles"],
    }
    cities = region_cities.get(region, [loc])

    results = []
    seen = set()

    # Build queries targeting both /in (profiles) and /company pages
    li_queries = []
    for city in cities[:3]:
        li_queries.append(f"site:linkedin.com/in {query} {city}")
        li_queries.append(f"site:linkedin.com/company {query} {city}")
    li_queries.append(f"site:linkedin.com {query} {loc} email contact")

    # DuckDuckGo pass
    for q in li_queries:
        if len(results) >= 200:
            break
        try:
            encoded = urllib.parse.quote(q)
            resp = requests.get(
                f"https://html.duckduckgo.com/html/?q={encoded}",
                headers=HEADERS, timeout=7
            )
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for block in soup.select(".result__body"):
                t = block.select_one(".result__title a")
                s = block.select_one(".result__snippet")
                if not t:
                    continue
                title = t.get_text(strip=True)
                href  = t.get("href", "")
                if "uddg=" in href:
                    href = urllib.parse.unquote(href.split("uddg=")[-1].split("&")[0])
                if href in seen or "linkedin.com" not in href:
                    continue
                seen.add(href)
                snippet = s.get_text(strip=True) if s else ""
                results.append({
                    "name":       title,
                    "email":      extract_email(snippet),
                    "phone":      extract_phone(snippet),
                    "source_url": href,
                    "platform":   "linkedin",
                    "snippet":    snippet[:200],
                    "interests":  detect_interests(title + " " + snippet, keywords),
                    "score":      0
                })
            time.sleep(0.8)
        except Exception as e:
            print(f"[LinkedIn Deep] DDG error: {e}")

    # Bing pass
    for city in cities[:2]:
        if len(results) >= 200:
            break
        try:
            q = f"site:linkedin.com {query} {city} contact"
            encoded = urllib.parse.quote(q)
            resp = requests.get(
                f"https://www.bing.com/search?q={encoded}&first=1",
                headers=HEADERS, timeout=7
            )
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for b in soup.select("li.b_algo"):
                h2 = b.find("h2")
                link_el = h2.find("a") if h2 else None
                if not link_el:
                    continue
                title = link_el.get_text(strip=True)
                href  = link_el.get("href", "")
                cite  = b.find("cite")
                if cite:
                    real = cite.get_text(strip=True)
                    if real and not real.startswith("http"):
                        real = "https://" + real.split(" ")[0]
                    href = real.split(" ")[0]
                if "bing.com" in href or href in seen or "linkedin.com" not in href:
                    continue
                seen.add(href)
                p = b.find("p")
                snippet = p.get_text(strip=True) if p else ""
                results.append({
                    "name":       title,
                    "email":      extract_email(snippet),
                    "phone":      extract_phone(snippet),
                    "source_url": href,
                    "platform":   "linkedin",
                    "snippet":    snippet[:200],
                    "interests":  detect_interests(title + " " + snippet, keywords),
                    "score":      0
                })
            time.sleep(0.8)
        except Exception as e:
            print(f"[LinkedIn Deep] Bing error: {e}")

    print(f"[LinkedIn Deep] Found {len(results)} results")
    return results


def search_google_maps(query, platform, region, keywords):
    """Source 4 — Google Maps business listings (via search)."""
    return _scrape_directory("google.com/maps", query, region, keywords, "Google Maps businesses")


def search_yellowpages(query, platform, region, keywords):
    """Source 5 — Yellow Pages directory."""
    return _scrape_directory("yellowpages", query, region, keywords, "Yellow Pages")


def search_yelp(query, platform, region, keywords):
    """Source 6 — Yelp business listings."""
    return _scrape_directory("yelp", query, region, keywords, "Yelp listings")


def search_tiktok(query, platform, region, keywords):
    """Source 7 — TikTok business/creator profiles."""
    return _scrape_directory("tiktok.com", query, region, keywords, "TikTok profiles")


def search_wikipedia(query, platform, region, keywords):
    """Source 8 — Wikipedia related entities."""
    return _scrape_directory("wikipedia.org", query, region, keywords, "Wikipedia")


def search_daleeluna(query, platform, region, keywords):
    """Source 9 — Daleeluna Lebanese business directory."""
    return _scrape_directory("daleeluna", query, region, keywords, "Daleeluna directory")


def search_yalla(query, platform, region, keywords):
    """Source 10 — Yalla / local Lebanese listings."""
    return _scrape_directory("lebanon-businesses OR lebanonyellowpages", query, region, keywords, "Lebanon listings")


def search_pinterest(query, platform, region, keywords):
    """Source 11 — Pinterest business profiles."""
    return _scrape_directory("pinterest.com", query, region, keywords, "Pinterest")


def search_youtube(query, platform, region, keywords):
    """Source 12 — YouTube channels/businesses."""
    return _scrape_directory("youtube.com", query, region, keywords, "YouTube channels")


def search_instagram_src(query, platform, region, keywords):
    """Source 13 — Instagram business profiles."""
    return _scrape_directory("instagram.com", query, region, keywords, "Instagram")


def search_foursquare(query, platform, region, keywords):
    """Source 14 — Foursquare venue listings."""
    return _scrape_directory("foursquare.com", query, region, keywords, "Foursquare")


def search_zomato(query, platform, region, keywords):
    """Source 15 — Zomato (food businesses)."""
    return _scrape_directory("zomato.com", query, region, keywords, "Zomato")


def search_tripadvisor(query, platform, region, keywords):
    """Source 16 — TripAdvisor businesses."""
    return _scrape_directory("tripadvisor.com", query, region, keywords, "TripAdvisor")


def search_crunchbase(query, platform, region, keywords):
    """Source 17 — Crunchbase company profiles."""
    return _scrape_directory("crunchbase.com", query, region, keywords, "Crunchbase")


def search_clutch(query, platform, region, keywords):
    """Source 18 — Clutch B2B company directory."""
    return _scrape_directory("clutch.co", query, region, keywords, "Clutch")


def search_yellowpages_global(query, platform, region, keywords):
    """Source 19 — Global business directories."""
    return _scrape_directory("yellow.place OR cylex OR cybo", query, region, keywords, "Global directories")


def search_opencorporates(query, platform, region, keywords):
    """Source 20 — OpenCorporates company registry."""
    return _scrape_directory("opencorporates.com OR companies registry", query, region, keywords, "Company registry")


def search_alibaba(query, platform, region, keywords):
    """Source 21 — Alibaba B2B wholesale marketplace."""
    return _scrape_directory("alibaba.com", query, region, keywords, "Alibaba")


def search_aliexpress(query, platform, region, keywords):
    """Source 22 — AliExpress marketplace."""
    return _scrape_directory("aliexpress.com", query, region, keywords, "AliExpress")


def search_noon(query, platform, region, keywords):
    """Source 23 — Noon (Gulf marketplace)."""
    return _scrape_directory("noon.com", query, region, keywords, "Noon")


def search_jumia(query, platform, region, keywords):
    """Source 24 — Jumia marketplace."""
    return _scrape_directory("jumia", query, region, keywords, "Jumia")


def search_marketplaces_extra(query, platform, region, keywords):
    """Source 25 — combined marketplace listings."""
    return _scrape_directory("(site:olx.com.lb OR site:dubizzle.com OR site:amazon.com OR site:ebay.com OR site:etsy.com)", query, region, keywords, "Marketplaces")


def search_b2b_directories(query, platform, region, keywords):
    """
    Sources 26+ — Professional B2B & business directories.
    Searches each major directory and combines results.
    """
    directories = [
        ("kompass.com",        "Kompass"),
        ("europages.com",      "Europages"),
        ("allbiz OR all.biz",  "AllBiz"),
        ("hotfrog.com",        "Hotfrog"),
        ("manta.com",          "Manta"),
        ("brownbook.net",      "Brownbook"),
        ("cylex.com",          "Cylex"),
        ("eworldtrade.com",    "eWorldTrade"),
        ("made-in-china.com",  "Made-in-China"),
        ("thomasnet.com",      "Thomasnet"),
        ("tradeindia.com",     "TradeIndia"),
        ("indiamart.com",      "IndiaMART"),
        ("business-directory-uk.co.uk", "UK Directory"),
        ("chamberofcommerce.com", "Chamber of Commerce"),
    ]
    all_results = []
    for site, name in directories:
        try:
            all_results += _scrape_directory(site, query, region, keywords, name)
        except Exception as e:
            print(f"[{name}] Error: {e}")
    return all_results


def generate_demo_results(keywords: list, platform: str, region: str) -> list:
    """Smart demo data based on keywords."""
    kw = " ".join(keywords).lower()
    region_label = {
        "lebanon": "Beirut, Lebanon", "mena": "Dubai, UAE",
        "gcc": "Riyadh, KSA", "global": "Global", "europe": "London, UK"
    }.get(region, "Lebanon")

    base_leads = [
        {"name": f"TechZone {region_label.split(',')[0]} — Electronics Store", "email": "info@techzone-lb.com", "phone": "+961 1 234 567", "source_url": "https://www.techzone-lb.com", "platform": "web", "snippet": f"Leading {kw} retailer in {region_label}.", "interests": detect_interests(kw, keywords)},
        {"name": f"AlphaTech Distributors — {kw.title()} Wholesale", "email": "sales@alphatech.me", "phone": "+961 3 456 789", "source_url": "https://www.linkedin.com/company/alphatech-distributors", "platform": "linkedin", "snippet": f"B2B wholesale distributor of {kw}.", "interests": detect_interests(kw, keywords)},
        {"name": f"{kw.title()} Traders Group — Public Facebook Group", "email": None, "phone": None, "source_url": "https://www.facebook.com/groups/techtraders.lb", "platform": "facebook", "snippet": f"Public Facebook group for {kw} buyers and sellers.", "interests": detect_interests(kw, keywords)},
        {"name": f"SmartDeal {region_label.split(',')[0]} — Gadget Reseller", "email": "contact@smartdeal.lb", "phone": "+961 70 123 456", "source_url": "https://www.smartdeal.lb", "platform": "web", "snippet": f"Specializing in {kw}. Retail and wholesale.", "interests": detect_interests(kw, keywords)},
        {"name": f"Nour Electronics — Yellow Pages {region_label.split(',')[0]}", "email": "nour.electronics@gmail.com", "phone": "+961 6 789 012", "source_url": "https://www.yellowpages.com.lb/nour-electronics", "platform": "yellowpages", "snippet": f"Established {kw} shop. Authorized dealer.", "interests": detect_interests(kw, keywords)},
        {"name": "MegaTech MENA — LinkedIn Company Page", "email": "hr@megatech.ae", "phone": "+971 4 000 1111", "source_url": "https://www.linkedin.com/company/megatech-mena", "platform": "linkedin", "snippet": f"Regional distributor of {kw} products across MENA.", "interests": detect_interests(kw, keywords)},
        {"name": f"Beirut {kw.title()} Market — Public Page", "email": None, "phone": "+961 1 999 888", "source_url": "https://www.facebook.com/BeirutTechMarket", "platform": "facebook", "snippet": f"Public marketplace for {kw} in Beirut.", "interests": detect_interests(kw, keywords)},
        {"name": f"ProGadget — Yelp Listing {region_label}", "email": "hello@progadget.com", "phone": "+961 3 777 555", "source_url": "https://www.yelp.com/biz/progadget-beirut", "platform": "yelp", "snippet": f"Top-rated {kw} shop. 4.8 stars.", "interests": detect_interests(kw, keywords)},
    ]
    if platform not in ("web", "all"):
        filtered = [l for l in base_leads if l["platform"] == platform]
        return filtered or base_leads
    return base_leads


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_email(text: str):
    m = EMAIL_RE.search(text or "")
    return m.group(0) if m else None

def extract_phone(text: str):
    m = PHONE_RE.search(text or "")
    return m.group(0).strip() if m else None

def detect_platform(url: str) -> str:
    u = url.lower()
    if "linkedin.com"  in u: return "linkedin"
    if "facebook.com"  in u: return "facebook"
    if "instagram.com" in u: return "instagram"
    if "twitter.com" in u or "x.com" in u: return "twitter"
    if "yellowpages"   in u: return "yellowpages"
    if "yelp.com"      in u: return "yelp"
    if "olx." in u or "dubizzle" in u: return "marketplace"
    if "amazon." in u or "ebay." in u or "etsy." in u: return "marketplace"
    if "google.com/maps" in u or "maps.google" in u: return "maps"
    return "web"

def detect_interests(text: str, keywords: list) -> str:
    text_lower = text.lower()
    found = []
    # Prioritize the user's own keywords first
    for kw in keywords:
        if kw.lower() in text_lower and kw not in found:
            found.append(kw)
    # Then add a matching standard category only if it directly relates to a keyword
    for category, terms in INTEREST_KEYWORDS.items():
        # only add this category if one of the user keywords belongs to it
        kw_in_category = any(k.lower() in terms or k.lower() == category for k in keywords)
        if kw_in_category and any(t in text_lower for t in terms) and category not in found:
            found.append(category)
    return ", ".join(found) if found else "general"

def compute_score(lead: dict, keywords: list) -> int:
    score = 50
    if lead.get("email"): score += 20
    if lead.get("phone"): score += 10
    text = (lead.get("name","") + " " + lead.get("snippet","")).lower()
    matches = sum(1 for kw in keywords if kw.lower() in text)
    score += min(matches * 5, 15)
    platform_bonus = {"linkedin": 5, "yellowpages": 3, "yelp": 3}
    score += platform_bonus.get(lead.get("platform",""), 0)
    return min(score, 100)

# ── DEEP ENRICHMENT — fetch top results in parallel to extract contacts ──────
def _enrich_one(r):
    """Fetch a single result page and fill in missing email/phone. Returns the (modified) dict."""
    url = r.get("source_url", "")
    if not url or not url.startswith("http"):
        return r
    if r.get("email") and r.get("phone"):
        return r
    try:
        resp = requests.get(url, headers=HEADERS, timeout=3)
        if resp.status_code != 200:
            return r
        text = resp.text

        if not r.get("email"):
            found_emails = EMAIL_RE.findall(text)
            clean = [e for e in found_emails if not any(
                x in e.lower() for x in ["example.", "yourdomain", ".png", ".jpg", "sentry", "wixpress"]
            )]
            if clean:
                r["email"] = clean[0]

        if not r.get("phone"):
            for p in PHONE_RE.findall(text):
                p = p.strip()
                digits = re.sub(r"\D", "", p)
                if "." in p:
                    continue
                if re.search(r"(19|20)\d{2}[-/]", p):
                    continue
                if re.search(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", p):
                    continue
                if 8 <= len(digits) <= 15 and len(set(digits)) > 3 and (
                    p.startswith("+") or p.startswith("00") or
                    p.startswith("0") or p.startswith("(") or
                    p.startswith("1-") or p.startswith("1 ")
                ):
                    r["phone"] = p
                    break
    except Exception:
        pass
    return r


def enrich_results(results, keywords=None, max_enrich=80):
    """Visit up to max_enrich result pages IN PARALLEL to extract missing emails/phones."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Only enrich results that are missing at least one contact field
    to_enrich = [r for r in results if not (r.get("email") and r.get("phone"))][:max_enrich]

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_enrich_one, r): r for r in to_enrich}
        for f in as_completed(futures):
            try:
                f.result()
            except Exception:
                pass

    print(f"[enrich] Enriched up to {len(to_enrich)} results in parallel")
    return results