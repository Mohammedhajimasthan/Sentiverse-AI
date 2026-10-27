import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as DocumentPicker from 'expo-document-picker';
import { StatusBar } from 'expo-status-bar';
import { createClient } from '@supabase/supabase-js';
import 'react-native-url-polyfill/auto';

const OVERVIEW_KEY = 'sentiverse-latest-analysis-overview';
const API_URL_KEY = 'sentiverse-api-base-url';
const DEFAULT_API_URL = Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://127.0.0.1:8000';
const COLORS = {
  background: '#f4f7fb',
  surface: '#ffffff',
  ink: '#14213d',
  muted: '#64748b',
  border: '#dce4ef',
  primary: '#3157d5',
  primarySoft: '#eaf0ff',
  green: '#13845b',
  red: '#bf4545',
};

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;
const supabase = supabaseUrl && supabaseAnonKey
  ? createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        storage: AsyncStorage,
        autoRefreshToken: true,
        persistSession: true,
        detectSessionInUrl: false,
      },
    })
  : null;

const NAV_ITEMS = [
  ['analysis', 'Analyze'],
  ['dashboard', 'Dashboard'],
  ['analytics', 'Analytics'],
  ['help', 'Help'],
  ['account', 'Account'],
];

function Button({ title, onPress, secondary = false, disabled = false }) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        secondary && styles.secondaryButton,
        disabled && styles.disabledButton,
        pressed && !disabled && styles.pressedButton,
      ]}
    >
      {disabled ? <ActivityIndicator color={secondary ? COLORS.primary : '#fff'} /> : (
        <Text style={[styles.buttonText, secondary && styles.secondaryButtonText]}>{title}</Text>
      )}
    </Pressable>
  );
}

function Panel({ title, children }) {
  return (
    <View style={styles.panel}>
      {title ? <Text style={styles.panelTitle}>{title}</Text> : null}
      {children}
    </View>
  );
}

function Field({ label, ...props }) {
  return (
    <View style={styles.fieldGroup}>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      <TextInput
        placeholderTextColor="#94a3b8"
        style={styles.input}
        {...props}
      />
    </View>
  );
}

function InfoLine({ label, value }) {
  if (value === undefined || value === null || value === '') return null;
  return (
    <View style={styles.infoLine}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue}>{String(value)}</Text>
    </View>
  );
}

function buildOverview(data) {
  return {
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
      ]),
    ),
    emotion_distribution: data.emotion_distribution,
    summary: data.summary,
    recommendations: data.recommendations,
    analyzed_at: new Date().toISOString(),
  };
}

function AnalysisResult({ data }) {
  if (!data) {
    return (
      <Panel title="Your results">
        <Text style={styles.muted}>Analysis results will appear here. Review text is processed by your Sentiverse backend.</Text>
      </Panel>
    );
  }

  if (data.analysis_type === 'page_document' && data.document_analysis) {
    const document = data.document_analysis;
    return (
      <Panel title={data.title || data.platform || 'Webpage analysis'}>
        <InfoLine label="Page sentiment" value={document.sentiment?.label} />
        <InfoLine label="Emotion" value={document.emotion?.emotion} />
        <InfoLine label="Aspects" value={(document.aspects || []).map((item) => `${item.aspect} (${item.sentiment})`).join(', ') || 'None detected'} />
        <Text style={styles.bodyText}>{document.explanation?.summary || data.message}</Text>
        <Text style={styles.caption}>Analyzed as one page, not an aggregate of customer reviews.</Text>
        {document.content_preview ? <Text style={styles.quote}>{document.content_preview}</Text> : null}
      </Panel>
    );
  }

  if (data.positive_terms || data.negative_terms || data.aspects && !data.review_quality) {
    return (
      <Panel title="Review explanation">
        <Text style={styles.bodyText}>{data.summary || 'No explanation is available.'}</Text>
        <InfoLine label="Positive terms" value={(data.positive_terms || []).join(', ') || 'None'} />
        <InfoLine label="Negative terms" value={(data.negative_terms || []).join(', ') || 'None'} />
        <InfoLine label="Key aspects" value={(data.aspects || []).join(', ') || 'None'} />
      </Panel>
    );
  }

  if (data.review_quality) {
    const quality = data.review_quality;
    const sentimentCounts = data.sentiment_counts || {};
    return (
      <>
        <Panel title="Analysis summary">
          <InfoLine label="Overall sentiment" value={data.overall_sentiment || 'Insufficient data'} />
          <InfoLine label="Source" value={data.source} />
          <InfoLine label="Reviews analyzed" value={quality.valid_reviews} />
          <Text style={styles.bodyText}>{data.summary || 'No summary is available for this dataset.'}</Text>
        </Panel>
        <Panel title="Review validation">
          <InfoLine label="Received" value={quality.total_received} />
          <InfoLine label="Valid" value={quality.valid_reviews} />
          <InfoLine label="Duplicates removed" value={quality.duplicates_removed} />
          <InfoLine label="Invalid" value={quality.invalid_reviews} />
          <InfoLine label="Suspicious signals" value={quality.suspicious_reviews} />
          <InfoLine label="Low confidence" value={quality.low_confidence_reviews} />
        </Panel>
        <Panel title="Sentiment">
          {Object.entries(sentimentCounts).length
            ? Object.entries(sentimentCounts).map(([label, count]) => (
                <InfoLine key={label} label={label} value={`${count} (${data.sentiment_distribution?.[label] ?? 'N/A'}%)`} />
              ))
            : <Text style={styles.muted}>Not enough valid reviews to calculate sentiment statistics.</Text>}
        </Panel>
        {Object.keys(data.rating_distribution || {}).length ? (
          <Panel title="Rating distribution">
            {Object.entries(data.rating_distribution).reverse().map(([rating, value]) => (
            <InfoLine key={rating} label={`${rating} stars`} value={`${value.count} (${value.percentage}%)`} />
            ))}
            <InfoLine label="Rating-sentiment agreement" value={data.rating_sentiment_agreement?.percentage == null ? 'N/A' : `${data.rating_sentiment_agreement.percentage}%`} />
          </Panel>
        ) : null}
        {Object.keys(data.emotion_distribution || {}).length ? (
          <Panel title="Emotion distribution">
            {Object.entries(data.emotion_distribution).map(([emotion, value]) => (
            <InfoLine key={emotion} label={emotion} value={`${value.count} (${value.percentage}%)`} />
            ))}
          </Panel>
        ) : null}
        {data.sentiment_drivers ? (
          <Panel title="What is driving sentiment?">
            <Text style={styles.caption}>Aspect patterns in review text are not proof of causation.</Text>
            {['positive', 'negative'].map((direction) => (
            <View key={direction} style={styles.driverGroup}>
              <Text style={styles.driverHeading}>{direction === 'positive' ? 'Top positive factors' : 'Top reported concerns'}</Text>
              {(data.sentiment_drivers[direction] || []).slice(0, 5).map((driver) => (
                <InfoLine key={driver.aspect} label={driver.aspect} value={`${driver.count} mentions · ${driver.share_of_valid_reviews ?? 0}%`} />
              ))}
              {!data.sentiment_drivers[direction]?.length ? <Text style={styles.muted}>No aspect-level evidence found.</Text> : null}
            </View>
            ))}
          </Panel>
        ) : null}
        {data.aspects?.length ? (
          <Panel title="Aspect analysis">
            {data.aspects.slice(0, 12).map((aspect) => (
              <InfoLine key={aspect.aspect} label={aspect.aspect} value={`${aspect.positive} positive · ${aspect.neutral} neutral · ${aspect.negative} negative`} />
            ))}
          </Panel>
        ) : null}
        {data.recommendations?.length ? (
          <Panel title="Recommendations">
            {data.recommendations.map((item, index) => (
              <Text key={`${index}-${item}`} style={styles.bullet}>•  {item}</Text>
            ))}
          </Panel>
        ) : null}
      </>
    );
  }

  return (
    <Panel title="Analysis result">
      {data.summary ? <Text style={styles.bodyText}>{data.summary}</Text> : null}
      {data.message ? <Text style={styles.bodyText}>{data.message}</Text> : null}
      {data.status ? <InfoLine label="Status" value={data.status} /> : null}
      {data.reviews_found !== undefined ? <InfoLine label="Reviews found" value={data.reviews_found} /> : null}
      {data.valid_reviews_found !== undefined ? <InfoLine label="Valid reviews" value={data.valid_reviews_found} /> : null}
    </Panel>
  );
}

export default function App() {
  const [screen, setScreen] = useState('analysis');
  const [sourceMode, setSourceMode] = useState('text');
  const [reviewText, setReviewText] = useState('');
  const [link, setLink] = useState('');
  const [apiBase, setApiBase] = useState(DEFAULT_API_URL);
  const [apiDraft, setApiDraft] = useState(DEFAULT_API_URL);
  const [result, setResult] = useState(null);
  const [overview, setOverview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [user, setUser] = useState(null);
  const [authMode, setAuthMode] = useState('login');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [authNotice, setAuthNotice] = useState('');
  const [history, setHistory] = useState([]);

  useEffect(() => {
    let active = true;
    AsyncStorage.multiGet([API_URL_KEY, OVERVIEW_KEY]).then((entries) => {
      if (!active) return;
      const savedApi = entries[0][1];
      if (savedApi) {
        setApiBase(savedApi);
        setApiDraft(savedApi);
      }
      if (entries[1][1]) setOverview(JSON.parse(entries[1][1]));
    }).catch((error) => {
      console.error('Could not restore local app data.', error);
      if (active) setNotice('Some saved app data could not be loaded.');
    });

    if (!supabase) return () => { active = false; };
    supabase.auth.getSession().then(({ data, error }) => {
      if (error) console.error('Could not restore the Supabase session.', error);
      if (active) setUser(data?.session?.user || null);
    }).catch((error) => console.error('Could not restore the Supabase session.', error));
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user || null);
    });
    return () => {
      active = false;
      listener.subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!user || !supabase) {
      setHistory([]);
      return;
    }
    let active = true;
    supabase.from('analysis_runs')
      .select('id, created_at, source, total_reviews, overall_sentiment')
      .eq('owner_id', user.id)
      .order('created_at', { ascending: false })
      .limit(20)
      .then(({ data, error }) => {
        if (error) throw error;
        if (active) setHistory(data || []);
      })
      .catch((error) => {
        console.error('Could not load cloud analysis history.', error);
        if (active) setAuthNotice(`Cloud history could not be loaded: ${error.message}`);
      });
    return () => { active = false; };
  }, [user]);

  const apiAddress = useMemo(() => apiBase.replace(/\/+$/, ''), [apiBase]);

  async function requestJson(path, options = {}) {
    let response;
    try {
      response = await fetch(`${apiAddress}${path}`, options);
    } catch (error) {
      throw new Error(`Could not connect to ${apiAddress}. Confirm the backend is running and this address is reachable from your phone or emulator.`);
    }
    let payload;
    try {
      payload = await response.json();
    } catch {
      throw new Error(`The backend returned an unreadable response (HTTP ${response.status}).`);
    }
    if (!response.ok) {
      throw new Error(payload.detail || `Request failed (HTTP ${response.status}).`);
    }
    return payload;
  }

  async function saveAnalysis(data) {
    setResult(data);
    if (data.review_quality) {
      const savedOverview = buildOverview(data);
      setOverview(savedOverview);
      try {
        await AsyncStorage.setItem(OVERVIEW_KEY, JSON.stringify(savedOverview));
      } catch (error) {
        console.error('Could not save the dashboard overview.', error);
        setNotice('Analysis succeeded, but the dashboard overview could not be saved on this device.');
      }
      if (user && supabase) {
        const { error } = await supabase.from('analysis_runs').insert({
          owner_id: user.id,
          source: savedOverview.source || 'Unknown',
          total_reviews: savedOverview.review_quality?.valid_reviews || 0,
          overall_sentiment: savedOverview.overall_sentiment || 'Insufficient data',
          payload: savedOverview,
        });
        if (error) {
          console.error('Could not save the aggregate analysis to Supabase.', error);
          setNotice(`Analysis is saved on this device, but cloud saving failed: ${error.message}`);
        } else {
          setNotice('Aggregate analysis saved. Individual review text was not uploaded.');
          const { data: rows, error: historyError } = await supabase
            .from('analysis_runs')
            .select('id, created_at, source, total_reviews, overall_sentiment')
            .eq('owner_id', user.id)
            .order('created_at', { ascending: false })
            .limit(20);
          if (!historyError) setHistory(rows || []);
        }
      }
    }
  }

  async function runRequest(path, options, successMessage = 'Analysis complete.') {
    setBusy(true);
    setNotice('');
    try {
      const data = await requestJson(path, options);
      await saveAnalysis(data);
      if (!user || !supabase) setNotice(successMessage);
    } catch (error) {
      console.error(`Sentiverse API request failed (${path}).`, error);
      setNotice(error.message || 'The request failed.');
    } finally {
      setBusy(false);
    }
  }

  function analyzeReviews() {
    if (!reviewText.trim()) {
      Alert.alert('Review text required', 'Enter one review or separate multiple reviews with a blank line.');
      return;
    }
    runRequest('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: reviewText.trim() }),
    });
  }

  function explainReview() {
    if (!reviewText.trim()) {
      Alert.alert('Review text required', 'Enter a review before asking for an explanation.');
      return;
    }
    runRequest('/api/explainability', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: reviewText.trim() }),
    }, 'Explanation ready.');
  }

  function analyzeLink() {
    if (!link.trim()) {
      Alert.alert('Link required', 'Paste a public webpage URL to analyze.');
      return;
    }
    runRequest('/api/analyze-link', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: link.trim() }),
    }, 'Link analysis complete.');
  }

  async function runDemo() {
    await runRequest('/api/demo', { method: 'GET' }, 'Synthetic demo analysis complete.');
  }

  async function pickReviewFile() {
    try {
      const picked = await DocumentPicker.getDocumentAsync({
        type: ['text/csv', 'application/json', 'application/x-ipynb+json'],
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (picked.canceled) return;
      const file = picked.assets?.[0];
      if (!file) throw new Error('No file was selected.');
      const extension = file.name.toLowerCase().split('.').pop();
      const isNotebook = extension === 'ipynb';
      if (!isNotebook && extension !== 'csv') {
        throw new Error('Choose a CSV or Jupyter Notebook (.ipynb) file.');
      }
      const form = new FormData();
      form.append('file', {
        uri: file.uri,
        name: file.name,
        type: isNotebook ? 'application/x-ipynb+json' : 'text/csv',
      });
      await runRequest(isNotebook ? '/api/notebook-analyze' : '/api/csv-analyze', {
        method: 'POST',
        body: form,
      }, `${isNotebook ? 'Notebook' : 'CSV'} analysis complete.`);
    } catch (error) {
      console.error('Could not select or upload the review file.', error);
      setNotice(error.message || 'Could not select the review file.');
    }
  }

  async function saveApiAddress() {
    const normalized = apiDraft.trim().replace(/\/+$/, '');
    if (!/^https?:\/\/[^/]+$/i.test(normalized)) {
      Alert.alert('Invalid backend address', 'Enter a base URL such as http://192.168.1.25:8000.');
      return;
    }
    try {
      await AsyncStorage.setItem(API_URL_KEY, normalized);
      setApiBase(normalized);
      setNotice(`Backend address saved: ${normalized}`);
    } catch (error) {
      console.error('Could not save the backend address.', error);
      setNotice('The backend address could not be saved.');
    }
  }

  async function submitAuth() {
    if (!supabase) {
      setAuthNotice('Supabase is not configured. Add EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY to mobile/.env.');
      return;
    }
    setBusy(true);
    setAuthNotice('');
    try {
      if (authMode === 'signup') {
        const { data, error } = await supabase.auth.signUp({
          email: email.trim(),
          password,
          options: { data: { full_name: name.trim() } },
        });
        if (error) throw error;
        setAuthNotice(data.session
          ? 'Account created and signed in.'
          : 'Account created. Confirm your email, then sign in.');
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
        if (error) throw error;
        setAuthNotice('Signed in. Aggregate analyses can now be saved to your account.');
      }
    } catch (error) {
      console.error('Supabase authentication failed.', error);
      setAuthNotice(error.message || 'Authentication failed.');
    } finally {
      setBusy(false);
    }
  }

  async function requestPasswordReset() {
    if (!supabase) {
      setAuthNotice('Supabase is not configured. Add the project URL and anon/public key first.');
      return;
    }
    if (!email.trim()) {
      Alert.alert('Email required', 'Enter your email address before requesting a password reset.');
      return;
    }
    setBusy(true);
    setAuthNotice('');
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email.trim());
      if (error) throw error;
      setAuthNotice('If the account exists, a password reset email has been sent. Follow the link to finish resetting your password.');
    } catch (error) {
      console.error('Could not request a password reset.', error);
      setAuthNotice(error.message || 'Password reset request failed.');
    } finally {
      setBusy(false);
    }
  }

  async function signOut() {
    if (!supabase) return;
    const { error } = await supabase.auth.signOut();
    if (error) {
      console.error('Could not sign out.', error);
      setAuthNotice(error.message || 'Sign out failed.');
    } else {
      setAuthNotice('Signed out.');
    }
  }

  function renderAnalysis() {
    return (
      <>
        <Text style={styles.heading}>Analyze feedback</Text>
        <Text style={styles.subtitle}>Turn customer reviews into clear sentiment and aspect insights.</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
          {[
            ['text', 'Paste reviews'],
            ['file', 'Upload file'],
            ['url', 'Analyze a link'],
            ['demo', 'Demo dataset'],
          ].map(([mode, label]) => (
            <Pressable
              key={mode}
              onPress={() => setSourceMode(mode)}
              style={[styles.chip, sourceMode === mode && styles.activeChip]}
            >
              <Text style={[styles.chipText, sourceMode === mode && styles.activeChipText]}>{label}</Text>
            </Pressable>
          ))}
        </ScrollView>

        {sourceMode === 'text' ? (
          <Panel title="Review text">
            <TextInput
              multiline
              value={reviewText}
              onChangeText={setReviewText}
              placeholder="Paste one review, or separate multiple reviews with a blank line..."
              placeholderTextColor="#94a3b8"
              textAlignVertical="top"
              style={[styles.input, styles.textArea]}
            />
            <Button title="Analyze reviews" onPress={analyzeReviews} disabled={busy} />
            <Button title="Explain a review" onPress={explainReview} disabled={busy} secondary />
          </Panel>
        ) : null}
        {sourceMode === 'file' ? (
          <Panel title="Upload review data">
            <Text style={styles.bodyText}>Choose a CSV with a review/text/comment/feedback/content column, or a Jupyter Notebook containing saved review tables or text. Notebook code is never executed.</Text>
            <Button title="Choose CSV or notebook" onPress={pickReviewFile} disabled={busy} />
          </Panel>
        ) : null}
        {sourceMode === 'url' ? (
          <Panel title="Analyze a public webpage">
            <Text style={styles.bodyText}>Review pages use identified review records. Other readable public pages are analyzed as one document. Private pages and access controls are not bypassed.</Text>
            <Field label="Webpage URL" value={link} onChangeText={setLink} placeholder="https://example.com/article" autoCapitalize="none" keyboardType="url" />
            <Button title="Analyze link" onPress={analyzeLink} disabled={busy} />
          </Panel>
        ) : null}
        {sourceMode === 'demo' ? (
          <Panel title="Synthetic demo dataset">
            <Text style={styles.bodyText}>Run a labeled synthetic dataset to explore the analysis. These examples are not real customer feedback.</Text>
            <Button title="Run demo analysis" onPress={runDemo} disabled={busy} />
          </Panel>
        ) : null}
        {notice ? <Text accessibilityRole="alert" style={styles.notice}>{notice}</Text> : null}
        <AnalysisResult data={result} />
      </>
    );
  }

  function renderDashboard() {
    const quality = overview?.review_quality;
    return (
      <>
        <Text style={styles.heading}>Executive dashboard</Text>
        <Text style={styles.subtitle}>Latest aggregate analysis saved on this device.</Text>
        {!overview || !quality?.valid_reviews ? (
          <Panel title="No analysis yet">
            <Text style={styles.bodyText}>Run a review analysis to see sentiment, aspects, and recommendations here.</Text>
            <Button title="Analyze reviews" onPress={() => setScreen('analysis')} />
          </Panel>
        ) : (
          <>
            <Panel title={overview.product || 'Latest analysis'}>
              <InfoLine label="Source" value={overview.source} />
              <InfoLine label="Valid reviews" value={quality.valid_reviews} />
              <InfoLine label="Overall sentiment" value={overview.overall_sentiment || 'N/A'} />
              <InfoLine label="Received / duplicates / invalid" value={`${quality.total_received} / ${quality.duplicates_removed} / ${quality.invalid_reviews}`} />
              {Object.entries(overview.sentiment_counts || {}).map(([sentiment, count]) => (
                <InfoLine key={sentiment} label={`${sentiment} reviews`} value={`${count} (${overview.sentiment_distribution?.[sentiment] ?? 'N/A'}%)`} />
              ))}
            </Panel>
            {overview.aspects?.length ? (
              <Panel title="Aspect analysis">
                {overview.aspects.slice(0, 12).map((aspect) => (
                  <InfoLine key={aspect.aspect} label={aspect.aspect} value={`${aspect.positive} positive · ${aspect.neutral} neutral · ${aspect.negative} negative`} />
                ))}
              </Panel>
            ) : null}
            {Object.keys(overview.rating_distribution || {}).length ? (
              <Panel title="Rating distribution">
                {Object.entries(overview.rating_distribution).reverse().map(([rating, value]) => (
                  <InfoLine key={rating} label={`${rating} stars`} value={`${value.count} (${value.percentage}%)`} />
                ))}
                <InfoLine label="Rating-sentiment agreement" value={overview.rating_sentiment_agreement?.percentage == null ? 'N/A' : `${overview.rating_sentiment_agreement.percentage}%`} />
              </Panel>
            ) : null}
            {Object.keys(overview.emotion_distribution || {}).length ? (
              <Panel title="Emotion distribution">
                {Object.entries(overview.emotion_distribution).map(([emotion, value]) => (
                  <InfoLine key={emotion} label={emotion} value={`${value.count} (${value.percentage}%)`} />
                ))}
              </Panel>
            ) : null}
            {overview.sentiment_drivers ? (
              <Panel title="What is driving sentiment?">
                <Text style={styles.caption}>Aspect patterns in review text are not proof of causation.</Text>
                {['positive', 'negative'].map((direction) => (
                  <View key={direction} style={styles.driverGroup}>
                    <Text style={styles.driverHeading}>{direction === 'positive' ? 'Top positive factors' : 'Top reported concerns'}</Text>
                    {(overview.sentiment_drivers[direction] || []).slice(0, 5).map((driver) => (
                      <InfoLine key={driver.aspect} label={driver.aspect} value={`${driver.count} mentions · ${driver.share_of_valid_reviews ?? 0}%`} />
                    ))}
                    {!overview.sentiment_drivers[direction]?.length ? <Text style={styles.muted}>No aspect-level evidence found.</Text> : null}
                  </View>
                ))}
              </Panel>
            ) : null}
            {overview.summary ? <Panel title="Evidence-based summary"><Text style={styles.bodyText}>{overview.summary}</Text></Panel> : null}
            {overview.recommendations?.length ? (
              <Panel title="Recommendations">
                {overview.recommendations.map((item, index) => <Text key={`${index}-${item}`} style={styles.bullet}>•  {item}</Text>)}
              </Panel>
            ) : null}
          </>
        )}
        <Panel title="Backend connection">
          <Text style={styles.bodyText}>Set the address of the computer running the FastAPI backend. On a physical phone, use that computer’s LAN IP address.</Text>
          <Field label="Backend base URL" value={apiDraft} onChangeText={setApiDraft} autoCapitalize="none" keyboardType="url" placeholder="http://192.168.1.25:8000" />
          <Button title="Save backend address" onPress={saveApiAddress} secondary />
        </Panel>
        {notice ? <Text style={styles.notice}>{notice}</Text> : null}
        <Panel title="Cloud analysis history">
          {!supabase ? (
            <Text style={styles.muted}>Configure Supabase environment variables to enable account sign-in and cloud history.</Text>
          ) : !user ? (
            <Text style={styles.muted}>Sign in from Account to view saved aggregate analyses.</Text>
          ) : history.length ? history.map((row) => (
            <View key={row.id} style={styles.historyRow}>
              <Text style={styles.bodyText}>{row.source || 'Unknown source'} · {row.total_reviews} valid reviews · {row.overall_sentiment || 'Unclassified'}</Text>
              <Text style={styles.caption}>{row.created_at ? new Date(row.created_at).toLocaleString() : 'Date unavailable'}</Text>
            </View>
          )) : <Text style={styles.muted}>No cloud-saved analyses found yet.</Text>}
        </Panel>
      </>
    );
  }

  function renderAnalytics() {
    return (
      <>
        <Text style={styles.heading}>Model analytics</Text>
        <Text style={styles.subtitle}>Evaluation results are shown only when measured against an independent labeled dataset.</Text>
        <Panel title="Evaluation status: not yet measured">
          <Text style={styles.bodyText}>Accuracy, precision, recall, F1 score, and confusion matrices are intentionally not reported until an independent labeled test dataset is configured.</Text>
        </Panel>
        <Panel title="Data integrity">
          <Text style={styles.bodyText}>Ratings are summarized separately from NLP sentiment. Suspicious-review signals indicate a quality concern, not proof of fraud. Sentiment drivers show associations in review text, not proof of causation.</Text>
        </Panel>
      </>
    );
  }

  function renderHelp() {
    return (
      <>
        <Text style={styles.heading}>Help & about</Text>
        <Text style={styles.subtitle}>Sentiverse AI · Customer feedback intelligence</Text>
        <Panel title="Quick guide">
          <Text style={styles.bullet}>1. Paste reviews, upload a CSV/notebook, analyze a public link, or try the synthetic demo.</Text>
          <Text style={styles.bullet}>2. Separate manual reviews with a blank line.</Text>
          <Text style={styles.bullet}>3. Review validation counts, sentiment, aspects, and recommendations.</Text>
          <Text style={styles.bullet}>4. Open Dashboard for the latest aggregate overview.</Text>
        </Panel>
        <Panel title="Link extraction limits">
          <Text style={styles.bodyText}>JavaScript-rendered, sign-in-only, and blocked pages may not be available. Sentiverse does not bypass sign-in, CAPTCHA, or anti-bot controls. Use a source-provided export or authorized API.</Text>
        </Panel>
        <Panel title="Privacy">
          <Text style={styles.bodyText}>Review text is sent to the configured analysis backend for processing. Only aggregate summaries are saved to Supabase. Uploaded files and individual review text are not uploaded to cloud history.</Text>
        </Panel>
        <Panel title="About Sentiverse AI">
          <Text style={styles.bodyText}>Sentiverse AI analyzes customer feedback to surface sentiment, product aspects, emotion signals, and suspicious-review patterns. The app uses a FastAPI backend and optional Supabase Auth and Postgres history.</Text>
        </Panel>
      </>
    );
  }

  function renderAccount() {
    return (
      <>
        <Text style={styles.heading}>Account</Text>
        <Text style={styles.subtitle}>Optional Supabase sign-in and aggregate cloud history.</Text>
        {!supabase ? (
          <Panel title="Supabase not configured">
            <Text style={styles.bodyText}>Add EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY to mobile/.env. Use only the anon/public key; never put a service_role key in the app.</Text>
          </Panel>
        ) : user ? (
          <Panel title="Signed in">
            <Text style={styles.bodyText}>{user.email}</Text>
            <Text style={styles.caption}>Only aggregate analysis summaries are saved to your account.</Text>
            <Button title="Sign out" onPress={signOut} secondary />
          </Panel>
        ) : (
          <Panel title={authMode === 'signup' ? 'Create account' : 'Sign in'}>
            <View style={styles.modeRow}>
              {['login', 'signup'].map((mode) => (
                <Pressable key={mode} onPress={() => { setAuthMode(mode); setAuthNotice(''); }} style={[styles.modeButton, authMode === mode && styles.modeButtonActive]}>
                  <Text style={[styles.modeText, authMode === mode && styles.modeTextActive]}>{mode === 'login' ? 'Sign in' : 'Sign up'}</Text>
                </Pressable>
              ))}
            </View>
            {authMode === 'signup' ? <Field label="Full name" value={name} onChangeText={setName} placeholder="Your name" /> : null}
            <Field label="Email" value={email} onChangeText={setEmail} placeholder="you@example.com" autoCapitalize="none" keyboardType="email-address" />
            <Field label="Password" value={password} onChangeText={setPassword} placeholder="Password" secureTextEntry />
            <Button title={authMode === 'signup' ? 'Create account' : 'Sign in'} onPress={submitAuth} disabled={busy} />
            {authMode === 'login' ? <Button title="Forgot password?" onPress={requestPasswordReset} disabled={busy} secondary /> : null}
          </Panel>
        )}
        {authNotice ? <Text accessibilityRole="alert" style={styles.notice}>{authNotice}</Text> : null}
        <Panel title="Privacy">
          <Text style={styles.bodyText}>Individual reviews and uploaded files are not sent to Supabase cloud storage. Cloud history contains aggregate counts and summaries only.</Text>
        </Panel>
      </>
    );
  }

  const activeTitle = NAV_ITEMS.find(([key]) => key === screen)?.[1] || 'Analyze';
  return (
    <KeyboardAvoidingView style={styles.root} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <StatusBar style="dark" />
      <View style={styles.header}>
        <View>
          <Text style={styles.brand}>Sentiverse AI</Text>
          <Text style={styles.headerCaption}>{activeTitle}</Text>
        </View>
        <View style={styles.brandMark}><Text style={styles.brandMarkText}>S</Text></View>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.navScroll} contentContainerStyle={styles.nav}>
        {NAV_ITEMS.map(([key, label]) => (
          <Pressable key={key} onPress={() => setScreen(key)} style={[styles.navItem, screen === key && styles.navItemActive]}>
            <Text style={[styles.navText, screen === key && styles.navTextActive]}>{label}</Text>
          </Pressable>
        ))}
      </ScrollView>
      <ScrollView
        style={styles.content}
        contentContainerStyle={styles.contentInner}
        keyboardShouldPersistTaps="handled"
      >
        {screen === 'analysis' ? renderAnalysis() : null}
        {screen === 'dashboard' ? renderDashboard() : null}
        {screen === 'analytics' ? renderAnalytics() : null}
        {screen === 'help' ? renderHelp() : null}
        {screen === 'account' ? renderAccount() : null}
        <Text style={styles.footer}>Sentiverse AI · Feedback intelligence</Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.background, paddingTop: Platform.OS === 'android' ? 28 : 54 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 20, paddingBottom: 14 },
  brand: { color: COLORS.ink, fontSize: 21, fontWeight: '800', letterSpacing: -0.5 },
  headerCaption: { color: COLORS.muted, fontSize: 12, marginTop: 2 },
  brandMark: { width: 38, height: 38, borderRadius: 13, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  brandMarkText: { color: '#fff', fontSize: 18, fontWeight: '800' },
  navScroll: { maxHeight: 50, flexGrow: 0, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  nav: { paddingHorizontal: 12, gap: 5, alignItems: 'center' },
  navItem: { paddingVertical: 11, paddingHorizontal: 13, borderRadius: 18 },
  navItemActive: { backgroundColor: COLORS.primarySoft },
  navText: { color: COLORS.muted, fontSize: 13, fontWeight: '600' },
  navTextActive: { color: COLORS.primary },
  content: { flex: 1 },
  contentInner: { padding: 18, paddingBottom: 36 },
  heading: { color: COLORS.ink, fontSize: 26, lineHeight: 32, fontWeight: '800', letterSpacing: -0.7, marginBottom: 5 },
  subtitle: { color: COLORS.muted, fontSize: 14, lineHeight: 21, marginBottom: 16 },
  chipRow: { gap: 8, paddingVertical: 4, paddingBottom: 14 },
  chip: { paddingVertical: 9, paddingHorizontal: 12, borderWidth: 1, borderColor: COLORS.border, borderRadius: 18, backgroundColor: COLORS.surface },
  activeChip: { borderColor: COLORS.primary, backgroundColor: COLORS.primarySoft },
  chipText: { color: COLORS.muted, fontWeight: '600', fontSize: 12 },
  activeChipText: { color: COLORS.primary },
  panel: { backgroundColor: COLORS.surface, borderRadius: 16, padding: 16, marginBottom: 12, borderWidth: 1, borderColor: COLORS.border },
  panelTitle: { color: COLORS.ink, fontWeight: '700', fontSize: 16, marginBottom: 11 },
  bodyText: { color: '#34445e', fontSize: 14, lineHeight: 21, marginBottom: 9 },
  muted: { color: COLORS.muted, fontSize: 14, lineHeight: 21 },
  caption: { color: COLORS.muted, fontSize: 12, lineHeight: 17, marginTop: 4 },
  quote: { color: '#34445e', fontSize: 13, lineHeight: 20, backgroundColor: COLORS.background, padding: 11, borderRadius: 9, marginTop: 10 },
  infoLine: { flexDirection: 'row', justifyContent: 'space-between', gap: 12, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#edf1f6' },
  infoLabel: { color: COLORS.muted, flex: 1, fontSize: 13 },
  infoValue: { color: COLORS.ink, flex: 1, textAlign: 'right', fontSize: 13, fontWeight: '600' },
  fieldGroup: { marginBottom: 12 },
  label: { color: COLORS.ink, fontWeight: '600', fontSize: 13, marginBottom: 6 },
  input: { borderWidth: 1, borderColor: COLORS.border, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 11, color: COLORS.ink, fontSize: 14, backgroundColor: '#fff' },
  textArea: { minHeight: 142, marginBottom: 12 },
  button: { minHeight: 44, backgroundColor: COLORS.primary, borderRadius: 10, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 15, paddingVertical: 11, marginTop: 4, marginBottom: 8 },
  secondaryButton: { backgroundColor: COLORS.primarySoft, borderWidth: 1, borderColor: '#cbd8ff' },
  buttonText: { color: '#fff', fontSize: 14, fontWeight: '700' },
  secondaryButtonText: { color: COLORS.primary },
  disabledButton: { opacity: 0.62 },
  pressedButton: { opacity: 0.82 },
  notice: { color: COLORS.primary, backgroundColor: COLORS.primarySoft, padding: 12, borderRadius: 10, marginBottom: 12, fontSize: 13, lineHeight: 19 },
  bullet: { color: '#34445e', fontSize: 14, lineHeight: 21, marginBottom: 8 },
  modeRow: { flexDirection: 'row', gap: 8, marginBottom: 14 },
  modeButton: { flex: 1, borderRadius: 9, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center', padding: 10 },
  modeButtonActive: { backgroundColor: COLORS.primarySoft, borderColor: COLORS.primary },
  modeText: { color: COLORS.muted, fontWeight: '600' },
  modeTextActive: { color: COLORS.primary },
  historyRow: { paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: '#edf1f6' },
  driverGroup: { marginTop: 10 },
  driverHeading: { color: COLORS.ink, fontWeight: '700', fontSize: 13, marginBottom: 4 },
  footer: { color: '#94a3b8', fontSize: 11, textAlign: 'center', marginTop: 10, marginBottom: 8 },
});
