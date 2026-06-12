# AI-Based Public Data & Lead Collection System
### CCE Final Year Project — 2025

---

## Tech Stack
- **Backend:** Python + Flask
- **Frontend:** HTML5 + Bootstrap 5 (served by Flask)
- **Database:** SQLite (built into Python)
- **Scraping:** requests + BeautifulSoup4
- **AI Integration:** Anthropic Claude API (optional, Step 3)

---

## Project Structure

```
lead_system/
├── app.py                  ← Main entry point — run this
├── requirements.txt        ← Python dependencies
├── database/
│   ├── db.py               ← SQLite setup and helpers
│   └── leads.db            ← Created automatically on first run
├── routes/
│   ├── dashboard.py        ← Home dashboard
│   ├── search.py           ← Step 1: Search module
│   ├── fetch.py            ← Step 2: Web scraping module
│   └── leads.py            ← Step 3: Leads CRUD API
├── services/
│   ├── search_service.py   ← Step 1 business logic (Bing search)
│   └── scraper_service.py  ← Step 2 business logic (BeautifulSoup)
└── templates/
    ├── base.html           ← Shared sidebar layout
    ├── dashboard.html      ← Home page
    ├── search.html         ← Step 1 UI
    ├── fetch.html          ← Step 2 UI
    └── leads.html          ← Step 3 UI (admin table)
```

---

## Setup Instructions (VS Code)

### 1. Open the folder in VS Code
```
File → Open Folder → select lead_system/
```

### 2. Create a virtual environment
```bash
python -m venv venv
```

### 3. Activate it
- **Windows:** `venv\Scripts\activate`
- **Mac/Linux:** `source venv/bin/activate`

### 4. Install dependencies
```bash
pip install -r requirements.txt
```

### 5. Run the app
```bash
python app.py
```

### 6. Open in browser
```
http://127.0.0.1:5000
```

---

## System Pipeline

```
Step 1 — Search & Research
  → User enters keywords + selects platform & region
  → System queries Bing for public data matching keywords
  → Results are parsed, deduplicated, and AI-scored
  → User queues relevant leads

Step 2 — Web Fetch & Scraping
  → User pastes a public URL
  → requests library fetches the page
  → BeautifulSoup parses HTML
  → Regex extracts emails, phones, social links
  → Lead is saved to SQLite database

Step 3 — Leads Database
  → Full admin table of all saved leads
  → Filter by platform, status, or keyword
  → Update lead status (New / Contacted / Qualified)
  → Export entire database to CSV
```

---

## API Endpoints

| Method | Endpoint            | Description               |
|--------|---------------------|---------------------------|
| GET    | /                   | Dashboard                 |
| GET    | /search/            | Search module UI          |
| POST   | /search/run         | Run a keyword search      |
| GET    | /fetch/             | Fetch module UI           |
| POST   | /fetch/scrape       | Scrape a URL              |
| GET    | /leads/             | Leads table UI            |
| GET    | /leads/all          | Get all leads (JSON)      |
| POST   | /leads/add          | Add a new lead            |
| POST   | /leads/update-status| Update lead status        |
| DELETE | /leads/delete/<id>  | Delete a lead             |
| GET    | /leads/stats        | Get summary stats (JSON)  |

---

## Ethics & Compliance Notes
- Only public data is accessed (no login, no private data)
- Polite 1-second delay between requests
- Compliant with GDPR principles for public data
- No scraping of platforms that prohibit it in their ToS
