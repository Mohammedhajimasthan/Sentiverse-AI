function renderCloudHistory(rows) {
  const panel = document.getElementById('saved-analyses');
  if (!panel) return;

  const heading = document.createElement('h2');
  heading.textContent = 'Cloud analysis history';
  panel.replaceChildren(heading);
  if (!rows.length) {
    const empty = document.createElement('p');
    empty.textContent = 'No cloud-saved analyses are available for this account yet.';
    panel.appendChild(empty);
    return;
  }

  const list = document.createElement('ul');
  list.className = 'plain-list';
  rows.forEach((row) => {
    const item = document.createElement('li');
    const date = row.created_at ? new Date(row.created_at).toLocaleString() : 'Date unavailable';
    item.textContent =
      `${date} · ${row.source || 'Unknown source'} · ${row.total_reviews} valid reviews · ` +
      `${row.overall_sentiment || 'Unclassified'}`;
    list.appendChild(item);
  });
  panel.appendChild(list);
}

window.addEventListener('sentiverse:cloud-history-loaded', (event) => {
  renderCloudHistory(event.detail || []);
});

window.addEventListener('sentiverse:cloud-history-updated', async () => {
  try {
    const rows = await window.SentiverseCloud?.loadRecentAnalyses?.();
    if (rows) renderCloudHistory(rows);
  } catch (error) {
    console.error('Could not refresh the saved analysis history.', error);
  }
});

document.addEventListener('DOMContentLoaded', () => {
  const status = document.getElementById('dashboard-status');
  const overview = document.getElementById('dashboard-overview');
  const driversPanel = document.getElementById('dashboard-drivers');
  const aspectsPanel = document.getElementById('dashboard-aspects');
  const ratingsPanel = document.getElementById('dashboard-ratings');
  const emotionsPanel = document.getElementById('dashboard-emotions');
  const summaryPanel = document.getElementById('dashboard-summary');
  let data;

  try {
    data = JSON.parse(localStorage.getItem('sentiverse-latest-analysis-overview') || 'null');
  } catch (error) {
    console.error('Could not read the saved dashboard overview.', error);
  }

  if (!data || !data.review_quality?.valid_reviews) {
    status.textContent = 'No completed review analysis is available in this browser yet.';
    const link = document.createElement('a');
    link.href = 'index.html';
    link.textContent = 'Analyze reviews or run the demo dataset';
    status.appendChild(document.createElement('br'));
    status.appendChild(link);
    return;
  }

  status.textContent =
    `${data.product ? `${data.product} · ` : ''}Source: ${data.source || 'Unknown'} · ` +
    `${data.review_quality.total_received} received · ${data.review_quality.valid_reviews} valid · ` +
    `${data.review_quality.duplicates_removed} duplicates removed · ${data.review_quality.invalid_reviews} invalid · ` +
    `${data.review_quality.suspicious_reviews} suspicious · ${data.review_quality.low_confidence_reviews} low-confidence`;

  const counts = data.sentiment_counts || {};
  const distribution = data.sentiment_distribution || {};
  const totalCard = document.createElement('div');
  totalCard.className = 'info-card';
  const totalLabel = document.createElement('span');
  totalLabel.textContent = 'Valid Reviews';
  const totalValue = document.createElement('strong');
  totalValue.textContent = String(data.review_quality.valid_reviews);
  totalCard.append(totalLabel, totalValue);
  overview.appendChild(totalCard);
  const overallCard = document.createElement('div');
  overallCard.className = 'info-card';
  const overallLabel = document.createElement('span');
  overallLabel.textContent = 'Overall Sentiment';
  const overallValue = document.createElement('strong');
  overallValue.textContent = data.overall_sentiment || 'N/A';
  overallCard.append(overallLabel, overallValue);
  overview.appendChild(overallCard);
  Object.entries(counts).forEach(([label, count]) => {
    const card = document.createElement('div');
    card.className = `info-card ${label.toLowerCase()}`;
    const name = document.createElement('span');
    name.textContent = `${label} Reviews`;
    const value = document.createElement('strong');
    const percentage = distribution[label];
    value.textContent = `${count}${percentage == null ? '' : ` · ${percentage}%`}`;
    card.append(name, value);
    overview.appendChild(card);
  });

  const driverHeading = document.createElement('h2');
  driverHeading.textContent = 'What is driving sentiment?';
  const driverNote = document.createElement('p');
  driverNote.textContent = 'Aspect-level patterns in the review text, not proof of causation.';
  driversPanel.replaceChildren(driverHeading, driverNote);
  const driverColumns = document.createElement('div');
  driverColumns.className = 'sentiment-driver-columns';
  [
    ['positive', 'Top positive factors'],
    ['negative', 'Top reported concerns'],
  ].forEach(([direction, label]) => {
    const group = document.createElement('div');
    group.className = `sentiment-driver-group ${direction}`;
    const heading = document.createElement('h3');
    heading.textContent = label;
    group.appendChild(heading);
    const drivers = data.sentiment_drivers?.[direction] || [];
    if (!drivers.length) {
      const empty = document.createElement('p');
      empty.textContent = 'No aspect-level evidence found.';
      group.appendChild(empty);
    }
    drivers.forEach((driver) => {
      const item = document.createElement('p');
      item.textContent =
        `${driver.aspect}: ${driver.count} ${direction} mentions ` +
        `(${driver.share_of_valid_reviews ?? 0}% of valid reviews)`;
      group.appendChild(item);
    });
    driverColumns.appendChild(group);
  });
  driversPanel.appendChild(driverColumns);

  if (Array.isArray(data.aspects) && data.aspects.length) {
    aspectsPanel.replaceChildren();
    const heading = document.createElement('h2');
    heading.textContent = 'Aspect analysis';
    aspectsPanel.appendChild(heading);
    const list = document.createElement('div');
    list.className = 'dash-list';
    data.aspects.forEach((aspect) => {
      const row = document.createElement('div');
      row.className = 'dash-row';
      const label = document.createElement('span');
      label.textContent = aspect.aspect;
      const values = document.createElement('strong');
      values.textContent = `${aspect.positive} positive · ${aspect.neutral} neutral · ${aspect.negative} negative · ${aspect.total} total`;
      row.append(label, values);
      list.appendChild(row);
    });
    aspectsPanel.appendChild(list);
  }

  if (data.rating_distribution) {
    ratingsPanel.replaceChildren();
    const heading = document.createElement('h2');
    heading.textContent = 'Rating distribution';
    ratingsPanel.appendChild(heading);
    const list = document.createElement('ul');
    Object.entries(data.rating_distribution).reverse().forEach(([rating, value]) => {
      const item = document.createElement('li');
      item.textContent = `${rating}★: ${value.count} (${value.percentage}%)`;
      list.appendChild(item);
    });
    const agreement = data.rating_sentiment_agreement?.percentage;
    const agreementText = document.createElement('p');
    agreementText.textContent = `Rating-sentiment agreement: ${agreement == null ? 'N/A' : `${agreement}%`}`;
    ratingsPanel.append(list, agreementText);
  }

  if (data.emotion_distribution && Object.keys(data.emotion_distribution).length) {
    emotionsPanel.replaceChildren();
    const heading = document.createElement('h2');
    heading.textContent = 'Emotion distribution';
    emotionsPanel.appendChild(heading);
    const list = document.createElement('ul');
    Object.entries(data.emotion_distribution).forEach(([emotion, value]) => {
      const item = document.createElement('li');
      item.textContent = `${emotion}: ${value.count} (${value.percentage}%)`;
      list.appendChild(item);
    });
    emotionsPanel.appendChild(list);
  }

  summaryPanel.replaceChildren();
  const summaryHeading = document.createElement('h2');
  summaryHeading.textContent = 'Evidence-based summary';
  const summary = document.createElement('p');
  summary.textContent = data.summary || 'Summary unavailable.';
  summaryPanel.append(summaryHeading, summary);
  if (Array.isArray(data.recommendations) && data.recommendations.length) {
    const list = document.createElement('ul');
    list.className = 'plain-list';
    data.recommendations.forEach((text) => {
      const item = document.createElement('li');
      item.textContent = text;
      list.appendChild(item);
    });
    summaryPanel.appendChild(list);
  }
});
