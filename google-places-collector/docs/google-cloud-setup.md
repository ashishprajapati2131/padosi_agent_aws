# Google Cloud setup

The collector calls only the official Places API (New) and the Geocoding API. The optional map uses the Maps JavaScript API with a separate browser key. Do not put the server key in the browser.

1. Create a Google Cloud project.
2. Enable **Places API (New)**.
3. Enable **Geocoding API**. Enable **Maps JavaScript API** only if you will show the embedded map.
4. Turn on billing for the project. These APIs do not run without it.
5. Create credentials.
   - A server API key for the backend (`GOOGLE_MAPS_API_KEY`).
   - An optional browser API key (`VITE_GOOGLE_MAPS_BROWSER_KEY`) if you want the map.
6. Restrict the keys.
   - Server key: IP address restriction, and API restriction to Places API (New) and Geocoding API only.
   - Browser key: HTTP referrer restriction for your site, and API restriction to Maps JavaScript API only.
   - Never ship the server key to React, Vite, or a built JavaScript bundle.
7. Copy `.env.example` to `.env` and set the variables. Leave `GOOGLE_MAPS_API_KEY` only on the server. Leave `VITE_GOOGLE_MAPS_BROWSER_KEY` empty to hide the map. The results table still works.
8. Check connectivity without printing a key:

```bash
cd backend
python scripts/check_google_config.py
curl -s http://localhost:8000/api/health
```

`/api/health` returns `google_configured: true` or `false`. It does not call Google. A real search needs the server key and a signed-in user. `scripts/check_google_config.py` does not call Google unless you pass `--live`, and `--live` refuses to run when the key is empty. Do not commit `.env`.

Pricing and field behavior change. Read [Google Maps Platform pricing](https://developers.google.com/maps/billing-and-pricing/pricing) and the Places API (New) documentation before you turn the key on in production. See `docs/cost-control.md`.
