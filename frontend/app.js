let API_BASE_URL = 'http://127.0.0.1:8000';

async function resolveApiBaseUrl() {
    const candidatePorts = [
        8000, 8001, 8002, 8003, 8004, 8005, 8006, 8007, 8008, 8009,
        8010, 8011, 8012, 8013, 8014, 8015, 8016, 8017, 8018, 8019,
        8080, 3000
    ];

    const uniquePorts = [...new Set(candidatePorts)];
    for (const port of uniquePorts) {
        const candidate = `http://127.0.0.1:${port}`;
        try {
            const response = await fetch(`${candidate}/api/health`, { method: 'GET' });
            if (response.ok) {
                API_BASE_URL = candidate;
                return candidate;
            }
        } catch (error) {
            // Port is unavailable; try the next candidate.
        }
    }

    return API_BASE_URL;
}

const reviewInput = document.getElementById('review-input');
const resultsDiv = document.getElementById('results');
const chartsDiv = document.getElementById('charts');
const modelMetricsDiv = document.getElementById('model-metrics');
const analyzeButton = document.getElementById('analyze-button');
const explainButton = document.getElementById('explain-button');
const analyzeLinkButton = document.getElementById('analyze-link-button');
const linkInput = document.getElementById('link-input');
const reviewFileInput = document.getElementById('review-file-input');
const demoAnalyzeButton = document.getElementById('demo-analyze-button');

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function renderPageDocumentAnalysis(data) {
    resultsDiv.innerHTML = '';
    const documentAnalysis = data.document_analysis;
    const card = document.createElement('article');
    card.className = 'result-card page-document-analysis';

    const heading = document.createElement('h3');
    heading.textContent = data.title || data.platform || 'Web page analysis';
    const source = document.createElement('p');
    source.textContent = `Source: ${data.source_url || 'URL unavailable'}`;
    const note = document.createElement('p');
    note.textContent = data.message || 'Visible webpage text analyzed as one document.';

    const overview = document.createElement('p');
    const confidence = Number(documentAnalysis.sentiment?.confidence);
    overview.textContent =
        `Page sentiment: ${documentAnalysis.sentiment?.label || 'Unknown'}` +
        (Number.isFinite(confidence) ? ` · confidence ${Math.round(confidence * 100)}%` : '') +
        ` · emotion: ${documentAnalysis.emotion?.emotion || 'Unknown'}`;
    card.append(heading, source, note, overview);

    const characterCount = document.createElement('p');
    characterCount.textContent =
        `Visible text analyzed: ${documentAnalysis.content_characters_analyzed} characters` +
        (documentAnalysis.content_truncated ? ' (content exceeded a fetch or analysis size limit)' : '');
    card.appendChild(characterCount);

    const aspectHeading = document.createElement('strong');
    aspectHeading.textContent = 'Topics/aspects detected';
    const aspectList = document.createElement('ul');
    (documentAnalysis.aspects || []).forEach((aspect) => {
        const item = document.createElement('li');
        item.textContent = `${aspect.aspect}: ${aspect.sentiment}`;
        aspectList.appendChild(item);
    });
    if (!aspectList.childElementCount) {
        const item = document.createElement('li');
        item.textContent = 'No known product/service aspects detected.';
        aspectList.appendChild(item);
    }
    card.append(aspectHeading, aspectList);

    if (documentAnalysis.explanation?.summary) {
        const explanation = document.createElement('p');
        explanation.textContent = documentAnalysis.explanation.summary;
        card.appendChild(explanation);
    }

    const previewHeading = document.createElement('strong');
    previewHeading.textContent = 'Extracted visible text preview';
    const preview = document.createElement('p');
    preview.className = 'document-text-preview';
    preview.textContent = documentAnalysis.content_preview || 'No visible text preview available.';
    card.append(previewHeading, preview);
    resultsDiv.appendChild(card);
}

function renderResults(data) {
    resultsDiv.innerHTML = '';

    if (!data || typeof data !== 'object') {
        resultsDiv.innerHTML = '<p>No analysis data returned.</p>';
        return;
    }

    if (data.analysis_type === 'page_document' && data.document_analysis) {
        renderPageDocumentAnalysis(data);
        return;
    }

    if (data.review_quality && (data.status || data.reviews)) {
        renderAggregateResults(data);
        return;
    }

    if (data.summary || data.insights) {
        const summaryBox = document.createElement('div');
        summaryBox.className = 'summary-box';

        const title = document.createElement('h3');
        title.textContent = 'Executive Summary';
        const summaryText = document.createElement('p');
        summaryText.textContent = data.summary || 'Summary unavailable.';

        summaryBox.appendChild(title);
        summaryBox.appendChild(summaryText);
        resultsDiv.appendChild(summaryBox);

        if (data.insights) {
            const insights = Array.isArray(data.insights) ? data.insights : data.insights.recommendations || [];
            const insightList = document.createElement('div');
            insightList.className = 'insight-list';

            insights.forEach((item) => {
                const card = document.createElement('div');
                card.className = 'result-card';
                card.textContent = typeof item === 'string' ? item : JSON.stringify(item);
                insightList.appendChild(card);
            });

            resultsDiv.appendChild(insightList);
        }
    }

    const contentEntries = Object.entries(data).filter(([key]) => !['summary', 'insights', 'dashboard'].includes(key));
    contentEntries.forEach(([key, value]) => {
        const block = document.createElement('div');
        block.className = 'result-card';

        const label = document.createElement('strong');
        label.textContent = `${key}: `;

        const rawText = document.createElement('span');
        rawText.textContent = typeof value === 'string' ? value : JSON.stringify(value);

        block.appendChild(label);
        block.appendChild(rawText);
        resultsDiv.appendChild(block);
    });
}

function renderAggregateResults(data) {
    const storedOverview = {
        source: data.source,
        product: data.product || null,
        total_reviews: data.total_reviews,
        overall_sentiment: data.overall_sentiment,
        sentiment_counts: data.sentiment_counts,
        sentiment_distribution: data.sentiment_distribution,
        review_quality: data.review_quality,
        rating_distribution: data.rating_distribution,
        rating_sentiment_agreement: data.rating_sentiment_agreement,
        aspects: (data.aspects || []).map(({ reviews, ...aspect }) => aspect),
        sentiment_drivers: Object.fromEntries(
            Object.entries(data.sentiment_drivers || {}).map(([direction, drivers]) => [
                direction,
                drivers.map(({ evidence, ...driver }) => driver),
            ])
        ),
        emotion_distribution: data.emotion_distribution,
        summary: data.summary,
        recommendations: data.recommendations,
        analyzed_at: new Date().toISOString(),
    };
    try {
        localStorage.setItem('sentiverse-latest-analysis-overview', JSON.stringify(storedOverview));
    } catch (error) {
        console.error('Could not save the analysis overview for the dashboard.', error);
    }
    window.dispatchEvent(new CustomEvent('sentiverse:analysis-ready', { detail: storedOverview }));

    const report = document.createElement('div');
    report.className = 'analysis-report';
    const addSection = (title, className = '') => {
        const section = document.createElement('section');
        section.className = `report-section ${className}`.trim();
        const heading = document.createElement('h3');
        heading.textContent = title;
        section.appendChild(heading);
        report.appendChild(section);
        return section;
    };
    const appendList = (container, values) => {
        const list = document.createElement('ul');
        values.forEach((value) => {
            const item = document.createElement('li');
            item.textContent = value;
            list.appendChild(item);
        });
        container.appendChild(list);
    };

    const summary = document.createElement('p');
    summary.textContent = data.summary || 'Summary unavailable.';
    addSection('Executive Summary', 'executive-summary').appendChild(summary);

    const sourceSection = addSection('Data source');
    const source = document.createElement('p');
    const sourceLabel = data.product ? `${data.product} · ` : '';
    source.textContent = `${sourceLabel}Source: ${data.source || 'Unknown'} · Reviews analyzed: ${data.review_quality.valid_reviews}`;
    sourceSection.appendChild(source);

    const quality = data.review_quality;
    const qualitySection = addSection('Review validation');
    appendList(qualitySection, [
        `Received: ${quality.total_received}`,
        `Valid: ${quality.valid_reviews}`,
        `Duplicates removed: ${quality.duplicates_removed}`,
        `Invalid: ${quality.invalid_reviews}`,
        `Suspicious signals: ${quality.suspicious_reviews}`,
        `Low-confidence predictions: ${quality.low_confidence_reviews}`,
    ]);

    if (data.sentiment_counts && Object.keys(data.sentiment_counts).length) {
        const sentiments = addSection(`Overall sentiment: ${data.overall_sentiment || 'Insufficient data'}`);
        const values = [];
        Object.entries(data.sentiment_counts).forEach(([label, count]) => {
            const percentage = data.sentiment_distribution?.[label];
            values.push(`${label}: ${count} (${percentage == null ? 'N/A' : `${percentage}%`})`);
        });
        appendList(sentiments, values);
    } else {
        const sentiments = addSection('Overall sentiment: Insufficient data');
        const noSentiment = document.createElement('p');
        noSentiment.textContent = 'Sentiment statistics are unavailable because there are not enough valid reviews to analyze.';
        sentiments.appendChild(noSentiment);
    }

    if (data.rating_distribution && Object.keys(data.rating_distribution).length) {
        const ratings = addSection('Rating distribution');
        const ratingValues = Object.entries(data.rating_distribution).reverse()
            .map(([rating, value]) => `${rating}★: ${value.count} (${value.percentage}%)`);
        appendList(ratings, ratingValues);
        const agreement = data.rating_sentiment_agreement?.percentage;
        const agreementText = document.createElement('p');
        agreementText.textContent = `Rating-sentiment agreement: ${agreement == null ? 'N/A' : `${agreement}%`} (${data.rating_sentiment_agreement?.count ?? 'N/A'} / ${data.rating_sentiment_agreement?.total_rated ?? 0} rated reviews)`;
        ratings.appendChild(agreementText);
    } else {
        const ratings = addSection('Rating distribution');
        const noRatings = document.createElement('p');
        noRatings.textContent = 'N/A — no valid star ratings were present in the input.';
        ratings.appendChild(noRatings);
    }

    const driverSection = addSection('Main factors associated with positive and negative feedback');
    const driverNote = document.createElement('p');
    driverNote.className = 'driver-caveat';
    driverNote.textContent = 'These are aspect-level patterns found in the reviews, not proof that an aspect caused a sentiment.';
    driverSection.appendChild(driverNote);
    const driverColumns = document.createElement('div');
    driverColumns.className = 'sentiment-driver-columns';
    [
        ['positive', 'Top positive factors'],
        ['negative', 'Top reported concerns'],
    ].forEach(([direction, label]) => {
        const group = document.createElement('div');
        group.className = `sentiment-driver-group ${direction}`;
        const groupHeading = document.createElement('h4');
        groupHeading.textContent = label;
        group.appendChild(groupHeading);
        const drivers = data.sentiment_drivers?.[direction] || [];
        if (!drivers.length) {
            const empty = document.createElement('p');
            empty.textContent = 'No aspect-level evidence was found.';
            group.appendChild(empty);
        } else {
            drivers.forEach((driver) => {
                const card = document.createElement('article');
                card.className = 'sentiment-driver-card';
                const title = document.createElement('strong');
                title.textContent = driver.aspect;
                const count = document.createElement('p');
                const validCount = data.review_quality?.valid_reviews || data.total_reviews || 0;
                count.textContent =
                    `${driver.count} ${direction} aspect mention${driver.count === 1 ? '' : 's'} ` +
                    `in ${validCount} valid reviews (${driver.share_of_valid_reviews ?? 0}%).`;
                card.append(title, count);
                (driver.evidence || []).forEach((review) => {
                    const quote = document.createElement('blockquote');
                    quote.textContent = review.text;
                    card.appendChild(quote);
                });
                group.appendChild(card);
            });
        }
        driverColumns.appendChild(group);
    });
    driverSection.appendChild(driverColumns);

    if (Array.isArray(data.aspects) && data.aspects.length) {
        const aspectSection = addSection('Aspect analysis and review evidence');
        const aspectList = document.createElement('div');
        aspectList.className = 'aspect-evidence-list';
        data.aspects.forEach((aspect) => {
            const details = document.createElement('details');
            const heading = document.createElement('summary');
            heading.textContent = `${aspect.aspect}: ${aspect.positive} positive · ${aspect.neutral} neutral · ${aspect.negative} negative · ${aspect.total} total mentions · view evidence`;
            details.appendChild(heading);
            (aspect.reviews || []).slice(0, 8).forEach((review) => {
                const evidence = document.createElement('p');
                evidence.textContent = `${review.sentiment} — ${review.text}`;
                details.appendChild(evidence);
            });
            aspectList.appendChild(details);
        });
        aspectSection.appendChild(aspectList);
    } else {
        const aspects = addSection('Aspect analysis and review evidence');
        const noAspects = document.createElement('p');
        noAspects.textContent = 'No product or service aspects were detected in the valid reviews.';
        aspects.appendChild(noAspects);
    }

    if (data.emotion_distribution && Object.keys(data.emotion_distribution).length) {
        const emotionSection = addSection('Emotion distribution');
        appendList(emotionSection, Object.entries(data.emotion_distribution)
            .map(([emotion, value]) => `${emotion}: ${value.count} (${value.percentage}%)`));
    } else {
        const emotions = addSection('Emotion distribution');
        const noEmotions = document.createElement('p');
        noEmotions.textContent = 'N/A — no emotion distribution is available for this dataset.';
        emotions.appendChild(noEmotions);
    }

    if (Array.isArray(data.recommendations) && data.recommendations.length) {
        const recommendations = addSection('Evidence-based recommendations');
        appendList(recommendations, data.recommendations);
    } else {
        const recommendations = addSection('Evidence-based recommendations');
        const noRecommendations = document.createElement('p');
        noRecommendations.textContent = 'No evidence-based recommendations are available for this dataset.';
        recommendations.appendChild(noRecommendations);
    }

    if (Array.isArray(data.reviews) && data.reviews.length) {
        const evidence = document.createElement('details');
        evidence.className = 'review-records';
        const title = document.createElement('summary');
        title.textContent = `Analyzed review records (${data.reviews.length})`;
        evidence.appendChild(title);
        const reviewList = document.createElement('ul');
        data.reviews.slice(0, 30).forEach((review) => {
            const item = document.createElement('li');
            const confidence = typeof review.sentiment?.confidence === 'number'
                ? `${Math.round(review.sentiment.confidence * 100)}%`
                : 'N/A';
            const suspicious = typeof review.suspicious_probability === 'number'
                ? `${Math.round(review.suspicious_probability * 100)}%`
                : 'N/A';
            item.textContent =
                `${review.review_id} · ${review.sentiment?.label || 'N/A'} · model confidence ${confidence} · ` +
                `rating ${review.rating ?? 'N/A'} · emotion ${review.emotion?.emotion || 'N/A'} · ` +
                `suspicious probability ${suspicious} · ${review.text}`;
            reviewList.appendChild(item);
        });
        evidence.appendChild(reviewList);
        if (data.reviews.length > 30) {
            const note = document.createElement('p');
            note.textContent = `Showing 30 of ${data.reviews.length} analyzed records.`;
            evidence.appendChild(note);
        }
        const recordSection = addSection('Review-level evidence');
        recordSection.appendChild(evidence);
    }
    resultsDiv.appendChild(report);
}

function renderDashboard(data) {
    chartsDiv.innerHTML = '';

    if (!data || typeof data !== 'object') {
        chartsDiv.innerHTML = '<p>Dashboard data unavailable.</p>';
        return;
    }

    if (!data.total_reviews) {
        chartsDiv.innerHTML = '<p>No analyzed review dataset is loaded. Analyze reviews or run Demo Analysis to populate this dashboard.</p>';
        return;
    }

    const summary = document.createElement('div');
    summary.className = 'dashboard-summary';

    const sentimentBreakdown = document.createElement('div');
    sentimentBreakdown.className = 'sentiment-breakdown';

    const sentimentOrder = ['Positive', 'Negative', 'Neutral', 'Mixed'];
    sentimentOrder.forEach((label) => {
        const value = Number(data.sentiment_distribution?.[label] ?? 0);
        const total = data.total_reviews || 1;
        const percentage = Math.round((value / total) * 100);

        const item = document.createElement('div');
        item.className = 'sentiment-bar-row';
        item.innerHTML = `
            <div class="bar-label"><span>${label}</span><span>${value}</span></div>
            <div class="bar-track"><div class="bar-fill ${label.toLowerCase()}" style="width: ${percentage}%"></div></div>
            <div class="bar-percent">${percentage}%</div>
        `;
        sentimentBreakdown.appendChild(item);
    });

    const aspects = document.createElement('div');
    aspects.className = 'aspect-chart';
    (data.top_aspects || []).forEach((item) => {
        const row = document.createElement('div');
        row.className = 'aspect-row';
        const maxCount = Math.max(...(data.top_aspects || []).map((entry) => Number(entry.count) || 0), 1);
        row.innerHTML = `
            <div class="aspect-meta">
                <span>${item.aspect}</span>
                <span>${item.count}</span>
            </div>
            <div class="bar-track"><div class="bar-fill aspect" style="width: ${((item.count || 0) / maxCount) * 100}%"></div></div>
        `;
        aspects.appendChild(row);
    });

    const percentages = ['positive', 'negative', 'neutral', 'mixed']
        .map((key) => data[key] == null ? 'N/A' : `${data[key]}%`);
    summary.innerHTML = `
        <h3>Overview</h3>
        <div class="stats-grid">
            <div class="stat-card"><span>Total Reviews</span><strong>${data.total_reviews}</strong></div>
            <div class="stat-card positive"><span>Positive</span><strong>${percentages[0]}</strong></div>
            <div class="stat-card negative"><span>Negative</span><strong>${percentages[1]}</strong></div>
            <div class="stat-card neutral"><span>Neutral</span><strong>${percentages[2]}</strong></div>
            <div class="stat-card"><span>Mixed</span><strong>${percentages[3]}</strong></div>
        </div>
    `;

    chartsDiv.appendChild(summary);
    chartsDiv.appendChild(sentimentBreakdown);

    const aspectPanel = document.createElement('div');
    aspectPanel.className = 'aspect-panel';
    aspectPanel.innerHTML = '<h3>Top Aspects</h3>';
    aspectPanel.appendChild(aspects);
    chartsDiv.appendChild(aspectPanel);

    const driverPanel = document.createElement('section');
    driverPanel.className = 'aspect-panel sentiment-driver-dashboard';
    const driverHeading = document.createElement('h3');
    driverHeading.textContent = 'What is driving sentiment?';
    driverPanel.appendChild(driverHeading);
    const driverNote = document.createElement('p');
    driverNote.textContent = 'Top review-mentioned factors associated with each sentiment; these are not causal conclusions.';
    driverPanel.appendChild(driverNote);
    const driverColumns = document.createElement('div');
    driverColumns.className = 'sentiment-driver-columns';
    [
        ['positive', 'Positive factors'],
        ['negative', 'Reported concerns'],
    ].forEach(([direction, label]) => {
        const group = document.createElement('div');
        group.className = `sentiment-driver-group ${direction}`;
        const heading = document.createElement('h4');
        heading.textContent = label;
        group.appendChild(heading);
        (data.sentiment_drivers?.[direction] || []).forEach((driver) => {
            const item = document.createElement('p');
            item.textContent = `${driver.aspect}: ${driver.count} ${direction} mentions (${driver.share_of_valid_reviews ?? 0}% of valid reviews)`;
            group.appendChild(item);
        });
        if (!group.querySelector('p')) {
            const empty = document.createElement('p');
            empty.textContent = 'No aspect-level evidence found.';
            group.appendChild(empty);
        }
        driverColumns.appendChild(group);
    });
    driverPanel.appendChild(driverColumns);
    chartsDiv.appendChild(driverPanel);
}

function renderModelMetrics(data) {
    modelMetricsDiv.innerHTML = '<h3>Model Performance</h3>';

    if (data?.status === 'not_evaluated') {
        const note = document.createElement('p');
        note.textContent = data.message;
        modelMetricsDiv.appendChild(note);
        return;
    }

    if (!data || typeof data !== 'object') {
        modelMetricsDiv.innerHTML += '<p>Model metrics unavailable.</p>';
        return;
    }

    if (data.message) {
        const note = document.createElement('p');
        note.textContent = data.message;
        modelMetricsDiv.appendChild(note);
    }

    const models = [];
    if (data.sentiment && typeof data.sentiment === 'object') {
        models.push({ name: 'Sentiment', stats: data.sentiment });
    }
    if (data.emotion && typeof data.emotion === 'object') {
        models.push({ name: 'Emotion', stats: data.emotion });
    }
    if (data.sarcasm && typeof data.sarcasm === 'object') {
        models.push({ name: 'Sarcasm', stats: data.sarcasm });
    }
    if (data.fake_review && typeof data.fake_review === 'object') {
        models.push({ name: 'Fake Review', stats: data.fake_review });
    }

    if (!models.length) {
        const singleMetrics = [
            { label: 'Accuracy', value: data.accuracy ?? 'n/a', suffix: '' },
            { label: 'Precision', value: data.precision ?? 'n/a', suffix: '' },
            { label: 'Recall', value: data.recall ?? 'n/a', suffix: '' },
            { label: 'F1 Score', value: data.f1_score ?? 'n/a', suffix: '' },
            { label: 'Dataset', value: data.dataset_size ?? 'n/a', suffix: ' reviews' },
        ];

        const grid = document.createElement('div');
        grid.className = 'metrics-grid';

        singleMetrics.forEach((metric) => {
            const card = document.createElement('div');
            card.className = 'metric-card';
            const value = typeof metric.value === 'number' ? metric.value.toFixed(4) : metric.value;
            card.innerHTML = `<span>${metric.label}</span><strong>${value}${metric.suffix}</strong>`;
            grid.appendChild(card);
        });

        modelMetricsDiv.appendChild(grid);
        return;
    }

    const summaryGrid = document.createElement('div');
    summaryGrid.className = 'metrics-grid';

    models.forEach(({ name, stats }) => {
        const card = document.createElement('div');
        card.className = 'metric-card';
        const accuracy = typeof stats.accuracy === 'number' ? stats.accuracy.toFixed(4) : 'n/a';
        const precision = typeof stats.precision === 'number' ? stats.precision.toFixed(4) : 'n/a';
        const recall = typeof stats.recall === 'number' ? stats.recall.toFixed(4) : 'n/a';
        const f1 = typeof stats.f1_score === 'number' ? stats.f1_score.toFixed(4) : 'n/a';
        card.innerHTML = `
            <span>${name}</span>
            <strong>${accuracy}</strong>
            <small>Accuracy</small>
            <div class='metric-mini'>P: ${precision} | R: ${recall} | F1: ${f1}</div>
        `;
        summaryGrid.appendChild(card);
    });

    modelMetricsDiv.appendChild(summaryGrid);
}

async function loadDashboard() {
    const baseUrl = await resolveApiBaseUrl();

    try {
        const [dashboardResponse, modelMetricsResponse] = await Promise.all([
            fetch(`${baseUrl}/api/dashboard`),
            fetch(`${baseUrl}/api/extended-model-metrics`)
        ]);

        const dashboardData = await dashboardResponse.json();
        const modelMetricsData = await modelMetricsResponse.json();

        renderDashboard(dashboardData);
        renderModelMetrics(modelMetricsData);
    } catch (error) {
        console.error(error);
        chartsDiv.innerHTML = '<p>Dashboard data could not be loaded.</p>';
        modelMetricsDiv.innerHTML = '<p>Model metrics could not be loaded.</p>';
    }
}

async function callEndpoint(endpoint, payload) {
    resultsDiv.innerHTML = '<p>Analyzing... Please wait.</p>';

    try {
        const baseUrl = await resolveApiBaseUrl();
        const response = await fetch(`${baseUrl}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(err.detail || 'Request failed');
        }

        const data = await response.json();
        renderResults(data);
        if (data.dashboard) {
            renderDashboard(data.dashboard);
        }
    } catch (error) {
        console.error(error);
        resultsDiv.innerHTML = `<p>${escapeHtml(error.message || 'Could not connect to the backend. Please ensure the server is running.')}</p>`;
    }
}

async function callEndpointForText(endpoint) {
    const text = reviewInput.value.trim();
    if (!text) {
        alert('Please enter a review before analyzing.');
        return;
    }
    await callEndpoint(endpoint, { text });
}

async function callExplainability() {
    const text = reviewInput.value.trim();
    if (!text) {
        alert('Please enter a review before asking the AI to explain its decision.');
        return;
    }

    resultsDiv.innerHTML = '<p>Generating explainability summary...</p>';

    try {
        const baseUrl = await resolveApiBaseUrl();
        const response = await fetch(`${baseUrl}/api/explainability`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Explainability failed' }));
            throw new Error(err.detail || 'Explainability failed');
        }

        const data = await response.json();
        resultsDiv.innerHTML = '';

        const summaryCard = document.createElement('div');
        summaryCard.className = 'result-card';
        summaryCard.innerHTML = `<strong>Explanation</strong>: ${escapeHtml(data.summary || 'No explanation available.')}`;
        resultsDiv.appendChild(summaryCard);

        const positiveCard = document.createElement('div');
        positiveCard.className = 'result-card';
        positiveCard.innerHTML = `<strong>Positive Terms</strong>: ${escapeHtml((data.positive_terms || []).join(', ') || 'None')}`;
        resultsDiv.appendChild(positiveCard);

        const negativeCard = document.createElement('div');
        negativeCard.className = 'result-card';
        negativeCard.innerHTML = `<strong>Negative Terms</strong>: ${escapeHtml((data.negative_terms || []).join(', ') || 'None')}`;
        resultsDiv.appendChild(negativeCard);

        const aspectsCard = document.createElement('div');
        aspectsCard.className = 'result-card';
        aspectsCard.innerHTML = `<strong>Key Aspects</strong>: ${escapeHtml((data.aspects || []).join(', ') || 'None')}`;
        resultsDiv.appendChild(aspectsCard);
    } catch (error) {
        console.error(error);
        resultsDiv.innerHTML = `<p>${escapeHtml(error.message || 'Explainability generation failed.')}</p>`;
    }
}

async function callAnalyzeLink() {
    const url = linkInput.value.trim();
    if (!url) {
        alert('Please paste a website, YouTube, or social link before extracting content.');
        return;
    }

    resultsDiv.innerHTML = '<p>Extracting content from link and analyzing it...</p>';

    try {
        const baseUrl = await resolveApiBaseUrl();
        const response = await fetch(`${baseUrl}/api/analyze-link`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Link extraction failed' }));
            throw new Error(err.detail || 'Link extraction failed');
        }

        const data = await response.json();
        if (data.analysis_type === 'page_document' && data.document_analysis) {
            renderResults(data);
            renderDashboard({ total_reviews: 0 });
            return;
        }
        if (!data.analysis) {
            resultsDiv.innerHTML = '';
            const statusCard = document.createElement('div');
            statusCard.className = 'result-card link-extraction-status';
            const statusHeading = document.createElement('h3');
            statusHeading.textContent = data.status === 'content_unavailable'
                ? 'Page content unavailable'
                : 'No review analysis generated';
            const statusText = document.createElement('p');
            statusText.textContent = data.message || 'Review text could not be extracted from this source.';
            const nextSteps = document.createElement('p');
            if (data.status === 'content_unavailable') {
                nextSteps.textContent =
                    'This can happen intermittently when a site serves a verification page, requires browser JavaScript ' +
                    'or sign-in, or limits automated requests. Try again later, or open the page in your browser and ' +
                    'paste its relevant text here. You can also use a source-provided export or authorized API. ' +
                    'Sentiverse does not bypass sign-in, CAPTCHA, or anti-bot restrictions.';
                statusCard.append(statusHeading, statusText, nextSteps);
            } else {
                const reviewCount = document.createElement('p');
                reviewCount.className = 'extraction-count';
                reviewCount.textContent =
                    `Review records found: ${data.reviews_found ?? 0} · ` +
                    `Valid reviews: ${data.valid_reviews_found ?? 0}`;
                nextSteps.textContent =
                    'To analyze customer feedback, paste the review text or upload a CSV with one review per row. ' +
                    'You can also import reviews using a source-provided export or authorized API.';
                statusCard.append(statusHeading, statusText, reviewCount, nextSteps);
            }
            resultsDiv.appendChild(statusCard);

            if (data.metadata_extracted) {
                const metadataCard = document.createElement('div');
                metadataCard.className = 'result-card';
                const metadataHeading = document.createElement('strong');
                metadataHeading.textContent = 'Page details';
                const metadata = document.createElement('p');
                const details = [data.platform, data.title || data.description || data.content_preview].filter(Boolean);
                metadata.textContent = details.join(' · ');
                metadataCard.append(metadataHeading, metadata);
                resultsDiv.appendChild(metadataCard);
            }
            renderDashboard({ total_reviews: 0 });
            return;
        }

        const analysis = {
            ...data.analysis,
            product: data.title,
            source: data.platform || 'URL',
        };
        renderResults(analysis);
        renderDashboard(data.analysis.dashboard);
    } catch (error) {
        console.error(error);
        resultsDiv.innerHTML = `<p>${escapeHtml(error.message || 'Link analysis failed.')}</p>`;
    }
}

async function callDemoAnalysis() {
    resultsDiv.innerHTML = '<p>Analyzing the clearly labeled synthetic demo dataset...</p>';
    try {
        const baseUrl = await resolveApiBaseUrl();
        const response = await fetch(`${baseUrl}/api/demo`);
        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Demo analysis failed' }));
            throw new Error(err.detail || 'Demo analysis failed');
        }
        const data = await response.json();
        renderResults(data);
        renderDashboard(data.dashboard);
    } catch (error) {
        console.error(error);
        resultsDiv.innerHTML = `<p>${escapeHtml(error.message || 'Demo analysis failed.')}</p>`;
    }
}

async function handleReviewFileUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    const isNotebook = file.name.toLowerCase().endsWith('.ipynb');
    const endpoint = isNotebook ? '/api/notebook-analyze' : '/api/csv-analyze';
    const uploadType = isNotebook ? 'notebook' : 'CSV';
    const formData = new FormData();
    formData.append('file', file);
    resultsDiv.innerHTML = `<p>Uploading ${uploadType} and analyzing reviews...</p>`;

    try {
        const baseUrl = await resolveApiBaseUrl();
        const response = await fetch(`${baseUrl}${endpoint}`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: `${uploadType} upload failed` }));
            throw new Error(err.detail || `${uploadType} upload failed`);
        }

        const data = await response.json();
        renderResults(data);
        renderDashboard(data.dashboard);
    } catch (error) {
        console.error(error);
        resultsDiv.innerHTML = `<p>${escapeHtml(error.message || `${uploadType} analysis failed.`)}</p>`;
    } finally {
        reviewFileInput.value = '';
    }
}

document.querySelectorAll('[data-source-mode]').forEach((tab) => {
    tab.addEventListener('click', () => {
        const mode = tab.dataset.sourceMode;
        document.querySelectorAll('[data-source-mode]').forEach((item) => {
            const active = item === tab;
            item.classList.toggle('active', active);
            item.setAttribute('aria-selected', String(active));
        });
        document.querySelectorAll('.source-panel').forEach((panel) => {
            const active = panel.id === `source-${mode}`;
            panel.classList.toggle('hidden', !active);
            panel.setAttribute('aria-hidden', String(!active));
        });
    });
});

analyzeButton.addEventListener('click', () => callEndpointForText('/api/analyze'));
explainButton.addEventListener('click', callExplainability);
analyzeLinkButton.addEventListener('click', callAnalyzeLink);
reviewFileInput.addEventListener('change', handleReviewFileUpload);
demoAnalyzeButton.addEventListener('click', callDemoAnalysis);

window.addEventListener('load', loadDashboard);
