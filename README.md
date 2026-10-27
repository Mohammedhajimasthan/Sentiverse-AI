# Sentiverse AI

Sentiverse AI is a local-first feedback analysis MVP built with FastAPI and a static HTML/CSS/JavaScript frontend. It analyzes review records from manual text, CSV files, Jupyter Notebooks, or supported structured review data on a URL, and can analyze readable public webpages as one document. Review aggregates and page-document analyses are identified separately.

## Data integrity

- For review aggregation, product titles, descriptions, specifications, metadata, and aggregate star counts are never passed to NLP as customer reviews. In page-document mode, visible page text (which may include product information) is analyzed as page content and is never presented as a review aggregate.
- URL analysis accepts review bodies exposed as Schema.org/JSON-LD `Review` objects or explicitly marked review-body elements, and direct CSV/JSON exports with a recognized review-text field. If a readable HTML or plain-text URL has no identified review records, visible webpage text is analyzed separately as one document; it is not presented as a review aggregate. It does not bypass sign-in, CAPTCHA, robots, or anti-bot controls.
- Link analysis accepts links without a scheme (it tries HTTPS), follows only redirects that pass the public-URL check, and preserves visible emoji text. For HTML, it prioritizes article/main content and skips common navigation, ads, sidebars, cookie banners, and hidden elements. Static HTML/plain-text responses are limited to 2 MB and 50,000 analyzed characters; truncation is reported. JavaScript-rendered page content, media transcripts, and private/blocked pages are not fetched or generated; the app reports when it has no readable content.
- CSV supports review-text columns such as `review`, `text`, `review_text`, `comment`, `feedback`, `message`, or `content`; optional IDs, ratings, dates, verification, author, helpful-vote, and product-ID fields are retained when present. Jupyter Notebook uploads extract saved review tables, Markdown cell text, and statically defined review literals; notebook code is never executed.
- Text validation cleans HTML, URLs, Unicode, and whitespace; removes empty/too-short and repetitive spam-like rows; and removes exact, reordered-token, and high-similarity duplicates.
- Dashboard counts and summaries are calculated from validated review records. Ratings are summarized separately from NLP sentiment, and rating agreement is only reported for records that include ratings.
- Sentiment drivers rank product/service aspects by positive and negative aspect-level review mentions, with matching example text. These are review-text associations, not proof that an aspect caused the sentiment.
- Confidence values come from the current lightweight models and are not calibrated probabilities. Suspicious-review output indicates a review-quality signal, not proof of fraud.
- Sentiment model performance is reported against the documented held-out UCI benchmark. Emotion, sarcasm, and suspicious-review performance remain **not independently evaluated**.

## Demo dataset

`GET /api/demo` runs 123 clearly labeled synthetic records derived from a small set of authored examples. It includes five rating levels and intentionally includes duplicate examples so the validation workflow can be demonstrated. Demo values are computed from the returned records and are not real customer or Amazon data.

## Run locally

1. Install dependencies: `pip install -r requirements.txt`
2. Start the API from the project root:

   ```powershell
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```

3. In another terminal, serve the frontend:

   ```powershell
   cd frontend
   python -m http.server 8080
   ```

4. Open `http://localhost:8080/index.html`.

The Analysis page has one input workspace with Paste reviews, Upload file, Analyze a link, and Demo dataset tabs. File uploads accept CSV review data and Jupyter Notebooks (`.ipynb`). CSV files need a review/text/comment/feedback/content column; notebooks can provide review tables in saved cell output or Markdown tables, review text in Markdown cells, or literal review lists in code cells. Notebook code is inspected but never executed. The frontend also includes Dashboard, Analytics, Help, About, and Login pages. The dashboard page shows aggregate results from the most recent analysis in this browser. Only aggregate counts, aspect summaries, and recommendations are retained in browser storage; individual review records and evidence snippets are not stored there.

## Expo mobile app

The native Expo app is in `mobile/`; it provides review text, CSV/Notebook, public link, and demo analysis, plus Dashboard, Analytics, Help, and optional Supabase account screens. It calls the existing FastAPI backend and stores only the latest aggregate dashboard overview on-device.

1. Start the backend so it is reachable by the phone:

   ```powershell
   python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```

2. In another terminal, start Expo:

   ```powershell
   cd mobile
   npm install
   npx expo start
   ```

3. Use Expo Go or an EAS development build to open the app. In the mobile Dashboard, set the backend base URL to `http://10.0.2.2:8000` for an Android emulator, `http://127.0.0.1:8000` for an iOS simulator, or `http://<computer-LAN-IP>:8000` for a physical device. A phone and the backend computer must be on the same network.

To enable Supabase Auth and aggregate history, copy `mobile/.env.example` to `mobile/.env`, fill in the project URL and anon/public key, and restart Expo. For EAS builds, configure `EXPO_PUBLIC_SUPABASE_URL` and `EXPO_PUBLIC_SUPABASE_ANON_KEY` as EAS environment variables. Never embed a Supabase `service_role` key in the app. The native app uses the same `analysis_runs` table and row-level security policy described above.

The Expo project is linked to EAS project `7cbfcb39-ec6e-4c90-a2b1-2c3c3422451b`. Create installable builds with `eas build --platform android` or `eas build --platform ios`.

## Supabase Auth and cloud history

Email/password authentication and cloud history are optional and disabled until configured. Sentiverse uses Supabase Auth directly; Firebase is not part of the authentication flow. The browser uses the Supabase project URL and **anon/public** key only. Never put a Supabase `service_role` key in frontend code.

1. Create a Supabase project and enable Email authentication under **Authentication → Providers**.
2. Under **Authentication → URL Configuration**, set the Site URL for your deployment and add the following callback URLs to the Redirect URLs allowlist (adjust host and port to match how the frontend is served):
   - `http://localhost:8080/auth.html`
   - `http://127.0.0.1:8080/auth.html`
   - `https://your-deployment-host/auth.html`
3. Copy the project URL and anon/public key from the Supabase project API settings into `frontend/cloud-config.js`:

   ```js
   window.SENTIVERSE_CLOUD_CONFIG = {
     supabase: {
       url: "https://YOUR_PROJECT_REF.supabase.co",
       anonKey: "YOUR_SUPABASE_ANON_KEY",
     },
   };
   ```

   The URL and anon/public key are intended for browser use. Row Level Security must remain enabled for user data.
4. Run this SQL in the Supabase SQL editor. It creates the aggregate-history table and replaces the earlier Firebase-claim policies with Supabase Auth user-ID policies. `owner_id` stays text for compatibility with the existing table schema.

   ```sql
   create table if not exists public.analysis_runs (
     id bigint generated always as identity primary key,
     owner_id text not null,
     created_at timestamptz not null default now(),
     source text not null,
     total_reviews integer not null,
     overall_sentiment text not null,
     payload jsonb not null
   );

   alter table public.analysis_runs enable row level security;

   drop policy if exists "Users can read their own analyses" on public.analysis_runs;
   drop policy if exists "Users can save their own analyses" on public.analysis_runs;

   create policy "Users can read their own analyses"
     on public.analysis_runs for select to authenticated
     using (owner_id = (select auth.uid()::text));

   create policy "Users can save their own analyses"
     on public.analysis_runs for insert to authenticated
     with check (owner_id = (select auth.uid()::text));

   grant select, insert on public.analysis_runs to authenticated;
   grant usage, select on sequence public.analysis_runs_id_seq to authenticated;
   ```

5. Reload the site, sign up or sign in, then run an analysis. If email confirmation is enabled, confirm the signup email before logging in. Signed-in users' aggregate summaries are saved to Supabase and listed on the Dashboard. Uploaded files, individual review records, and evidence text are not sent to Supabase. Cloud history errors are shown in the UI while the local analysis remains available.

Firebase accounts, passwords, and existing Firebase-owned history are not migrated automatically. Users must create or confirm a Supabase Auth account; any required history migration must be performed separately without weakening row-level security.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Backend health check |
| `POST` | `/api/analyze` | Analyze one review or blank-line-separated manual reviews |
| `POST` | `/api/analyze/reviews` | Analyze a list of manual review strings |
| `POST` | `/api/batch-analyze` | Batch review analysis |
| `POST` | `/api/csv-analyze` | Analyze an uploaded CSV (`file` form field) |
| `POST` | `/api/notebook-analyze` | Extract saved review tables and review text from an uploaded Jupyter Notebook (`file` form field; never executes code) |
| `POST` | `/api/analyze-link` | Analyze identified review records or visible HTML/plain-text page content as a single document |
| `GET` | `/api/demo` | Run the labeled synthetic demo dataset |
| `POST` | `/api/summarize` | Summarize submitted reviews after validation |
| `POST` | `/api/explainability` | Explain sentiment cues for one review |
| `GET` | `/api/dashboard` | Empty-state response; latest aggregate is kept in browser storage |
| `GET` | `/api/model-metrics`, `/api/extended-model-metrics` | Sentiment benchmark metrics when generated; explicitly marks the other models as not independently evaluated |
| `POST` | `/api/aspect-extraction` | Extract aspects from one review |
| `POST` | `/api/emotion-detection` | Detect emotion in one review |
| `POST` | `/api/sarcasm-detection` | Detect sarcasm in one review |
| `POST` | `/api/fake-review-detection` | Return a suspicious-review signal for one review |

## Analysis response

Batch, CSV, structured-review URL, and demo responses include:

- `review_quality`: received, valid, duplicate, invalid, low-confidence, and suspicious counts
- `reviews`: each unique valid review and its sentiment, confidence, aspects, emotion, rating, and quality signal
- `sentiment_counts` / `sentiment_distribution`: counts and percentages calculated from included review records
- `sentiment_drivers`: the top aspects associated with positive/negative aspect-level sentiment, including counts, valid-review shares, and representative review evidence; the nested dashboard copy omits evidence text
- `rating_distribution` / `rating_sentiment_agreement`: only when valid ratings are available
- `aspects`: mention counts by aspect/sentiment with representative review evidence
- `emotion_distribution`, `summary`, and evidence-based recommendations

When `/api/analyze-link` finds no structured review records on an HTML/plain-text page, it returns `analysis_type: "page_document"` with page-level sentiment, emotion, detected aspects, extraction counts, and a visible-text preview. This is a single-document result, not a customer-review aggregate. Known access/verification interstitials are reported as `status: "content_unavailable"` and are not analyzed as page content. Sign-in, CAPTCHA, and anti-bot restrictions are not bypassed; JavaScript-rendered or access-controlled content may remain unavailable.

Aspect extraction only reports aspects mentioned by review text; it does not add generic aspects to every review. The current NLP models are lightweight experimental components and should not be described as production-accurate without external labeled evaluation.

## Tests

Run the focused pipeline tests (Python standard library):

```powershell
python -m unittest backend.test_review_pipeline backend.test_external_evaluation_dataset -v
```

The tests cover review-only URL extraction, product-metadata separation, duplicate/invalid handling, rating aggregation, demo data availability, and the external evaluation data preparation/evaluation logic.

## Independent sentiment evaluation dataset

Prepare a local copy of the UCI Sentiment Labelled Sentences dataset:

```powershell
python -m backend.models.prepare_evaluation_dataset
python -m backend.models.evaluate_sentiment_model
```

The preparation command downloads UCI dataset 331 (DOI `10.24432/C57604`), validates the expected three domains and labels, and writes `datasets/sentiment_labelled_sentences.csv` plus a metadata sidecar. It creates a deterministic 80/20 development/test split within each domain and label, checks that duplicate text does not cross splits, and records any repaired/rejected source rows in the metadata. The evaluation command scores only the held-out test split and writes per-domain and overall metrics to `results/sentiment_uci_evaluation.json` and the compatibility copy `models/sentiment_metrics.json`. The older `models/extended_model_metrics.json` snapshot uses very small hand-authored examples and is not independent performance evidence; the API therefore reports only sentiment as evaluated.

The UCI dataset contains 3,000 English sentence snippets selected from Amazon, IMDb, and Yelp reviews, with positive/negative labels. It is binary and sentence-level, and is not a benchmark for neutral sentiment or the other analysis modules. The retrieved UCI metadata did not declare a license; check the source's applicable terms before use and do not redistribute the locally prepared corpus. Cite Kotzias et al., “From Group to Individual Labels Using Deep Features,” KDD 2015, UCI DOI `10.24432/C57604`.

## Current limitations

- URL extraction relies on structured review markup and may find no reviews on Amazon, social networks, or JavaScript-rendered pages. This is reported rather than worked around.
- Aspect, sentiment, emotion, and suspicious-review models remain small-data/heuristic MVP components.
- Results are not persisted server-side. The browser dashboard retains only the latest aggregate overview; reload the analysis page and run another input to replace it.
- Supabase Auth and aggregate-history persistence work only after project configuration and database row-level security are in place; review files and individual review text are not stored in Supabase.
