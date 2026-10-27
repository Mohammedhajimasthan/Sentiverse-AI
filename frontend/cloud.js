const cloudConfig = window.SENTIVERSE_CLOUD_CONFIG || {};
const supabaseConfig = cloudConfig.supabase || {};
const supabaseConfigured = typeof supabaseConfig.url === 'string'
    && supabaseConfig.url.startsWith('https://')
    && typeof supabaseConfig.anonKey === 'string'
    && Boolean(supabaseConfig.anonKey.trim());

let currentUser = null;
let supabase = null;

function setCloudStatus(message, isError = false) {
    const status = document.getElementById('cloud-status');
    if (!status) return;
    status.textContent = message;
    status.classList.toggle('error', isError);
}

function setAccountLink(user) {
    const links = document.querySelector('.nav-links');
    const accountLink = links?.querySelector('[data-account-link]')
        || links?.querySelector('a[href="auth.html"]');
    if (!links || !accountLink) return;

    accountLink.dataset.accountLink = 'true';
    accountLink.textContent = user ? user.email || 'Account' : 'Login';
    accountLink.href = user ? 'dashboard.html' : 'auth.html';

    let signOutButton = links.querySelector('[data-cloud-signout]');
    if (user && !signOutButton) {
        signOutButton = document.createElement('button');
        signOutButton.type = 'button';
        signOutButton.className = 'nav-link nav-button';
        signOutButton.dataset.cloudSignout = 'true';
        signOutButton.textContent = 'Sign out';
        signOutButton.addEventListener('click', async () => {
            try {
                const { error } = await supabase.auth.signOut();
                if (error) throw error;
                if (window.location.pathname.endsWith('/dashboard.html')) {
                    window.location.href = 'index.html';
                }
            } catch (error) {
                console.error('Could not sign out.', error);
                setCloudStatus(error.message || 'Sign out failed.', true);
            }
        });
        links.appendChild(signOutButton);
    } else if (!user && signOutButton) {
        signOutButton.remove();
    }
}

async function saveAggregate(aggregate) {
    if (!currentUser || !supabase) return;

    const { error } = await supabase.from('analysis_runs').insert({
        owner_id: currentUser.id,
        source: aggregate.source || 'Unknown',
        total_reviews: aggregate.review_quality?.valid_reviews || 0,
        overall_sentiment: aggregate.overall_sentiment || 'Insufficient data',
        payload: aggregate,
    });
    if (error) {
        console.error('Could not save the aggregate analysis to Supabase.', error);
        setCloudStatus(`Analysis is saved in this browser, but cloud saving failed: ${error.message}`, true);
        return;
    }

    setCloudStatus('Aggregate analysis saved to your account. Individual review text was not uploaded.');
    window.dispatchEvent(new CustomEvent('sentiverse:cloud-history-updated'));
}

async function loadRecentAnalyses(limit = 20) {
    if (!currentUser || !supabase) return [];

    const { data, error } = await supabase
        .from('analysis_runs')
        .select('id, created_at, source, total_reviews, overall_sentiment, payload')
        .eq('owner_id', currentUser.id)
        .order('created_at', { ascending: false })
        .limit(limit);
    if (error) {
        console.error('Could not load saved analyses from Supabase.', error);
        setCloudStatus(`Cloud analysis history could not be loaded: ${error.message}`, true);
        throw error;
    }
    return data || [];
}

window.SentiverseCloud = {
    getCurrentUser: () => currentUser,
    isConfigured: supabaseConfigured,
    loadRecentAnalyses,
};

window.addEventListener('sentiverse:analysis-ready', (event) => {
    if (event.detail) {
        saveAggregate(event.detail).catch((error) => {
            console.error('Could not save the aggregate analysis.', error);
            setCloudStatus('Analysis is available locally, but cloud saving failed.', true);
        });
    }
});

window.addEventListener('sentiverse:auth-state-changed', () => {
    if (currentUser && supabase) {
        loadRecentAnalyses().then((rows) => {
            window.dispatchEvent(new CustomEvent('sentiverse:cloud-history-loaded', { detail: rows }));
        }).catch((error) => {
            console.error('Could not load cloud analysis history.', error);
        });
    }
});

async function initializeCloudServices() {
    const authForm = document.getElementById('auth-form');
    const authStatus = document.getElementById('auth-status');
    const setAuthStatus = (message, isError = false) => {
        if (authStatus) {
            authStatus.textContent = message;
            authStatus.classList.toggle('error', isError);
        }
        setCloudStatus(message, isError);
    };

    if (authForm) {
        authForm.addEventListener('submit', async (event) => {
            event.preventDefault();
            if (!supabase) {
                setAuthStatus(
                    supabaseConfigured
                        ? 'Supabase is still initializing. Check your network, then try again.'
                        : 'Supabase is not configured. Add the project URL and anon key to frontend/cloud-config.js.',
                    true
                );
                return;
            }

            const email = authForm.querySelector('#email')?.value.trim() || '';
            const password = authForm.querySelector('#password')?.value || '';
            const name = authForm.querySelector('#name')?.value.trim() || '';
            const mode = authForm.dataset.mode || 'login';
            const submitButton = authForm.querySelector('button[type="submit"]');
            if (submitButton) submitButton.disabled = true;

            try {
                if (mode === 'update-password') {
                    const { error } = await supabase.auth.updateUser({ password });
                    if (error) throw error;
                    setAuthStatus('Your password has been updated. You can now sign in.');
                    window.location.href = 'dashboard.html';
                    return;
                }

                if (mode === 'signup') {
                    const { data, error } = await supabase.auth.signUp({
                        email,
                        password,
                        options: {
                            data: { full_name: name },
                            emailRedirectTo: `${window.location.origin}/auth.html`,
                        },
                    });
                    if (error) throw error;
                    if (!data.session) {
                        setAuthStatus('Account created. Confirm your email, then return here to sign in.');
                        return;
                    }
                } else {
                    const { error } = await supabase.auth.signInWithPassword({ email, password });
                    if (error) throw error;
                }

                window.location.href = 'dashboard.html';
            } catch (error) {
                console.error('Supabase authentication failed.', error);
                setAuthStatus(error.message || 'Authentication failed.', true);
            } finally {
                if (submitButton) submitButton.disabled = false;
            }
        });
    }

    document.getElementById('password-reset')?.addEventListener('click', async () => {
        if (!supabase) {
            setAuthStatus(
                supabaseConfigured
                    ? 'Supabase is still initializing. Check your network, then try again.'
                    : 'Configure Supabase before requesting a password reset.',
                true
            );
            return;
        }
        const email = document.getElementById('email')?.value.trim() || '';
        if (!email) {
            setAuthStatus('Enter your email address first, then request a password reset.', true);
            return;
        }
        try {
            const { error } = await supabase.auth.resetPasswordForEmail(email, {
                redirectTo: `${window.location.origin}/auth.html`,
            });
            if (error) throw error;
            setAuthStatus('Password reset email sent. Follow its link to choose a new password.');
        } catch (error) {
            console.error('Supabase password reset failed.', error);
            setAuthStatus(error.message || 'Password reset could not be sent.', true);
        }
    });

    if (!supabaseConfigured) {
        if (authStatus) {
            setAuthStatus('Supabase is not configured yet. Add the project URL and anon key to frontend/cloud-config.js.');
        }
        window.dispatchEvent(new CustomEvent('sentiverse:cloud-ready'));
        return;
    }

    try {
        const { createClient } = await import('https://esm.sh/@supabase/supabase-js@2.49.1');
        supabase = createClient(supabaseConfig.url, supabaseConfig.anonKey);

        const authFormTabs = document.querySelectorAll('[data-auth-tab]');
        const passwordResetButton = document.getElementById('password-reset');
        supabase.auth.onAuthStateChange((event, session) => {
            currentUser = session?.user || null;
            setAccountLink(currentUser);

            if (event === 'PASSWORD_RECOVERY' && authForm) {
                authForm.dataset.mode = 'update-password';
                const nameGroup = authForm.querySelector('#name-group');
                nameGroup?.classList.add('hidden');
                const nameInput = nameGroup?.querySelector('input');
                if (nameInput) nameInput.required = false;
                const emailInput = authForm.querySelector('#email');
                emailInput?.closest('.field-group')?.classList.add('hidden');
                if (emailInput) emailInput.required = false;
                const passwordLabel = authForm.querySelector('label[for="password"]');
                if (passwordLabel) passwordLabel.textContent = 'New password';
                const passwordInput = authForm.querySelector('#password');
                if (passwordInput) {
                    passwordInput.value = '';
                    passwordInput.placeholder = 'Enter your new password';
                    passwordInput.autocomplete = 'new-password';
                }
                const submitButton = authForm.querySelector('button[type="submit"]');
                if (submitButton) submitButton.textContent = 'Update password';
                authFormTabs.forEach((tab) => { tab.hidden = true; });
                if (passwordResetButton) passwordResetButton.hidden = true;
                setAuthStatus('Choose a new password for your account.');
            } else if (currentUser) {
                setAuthStatus(
                    `Signed in as ${currentUser.email}. Aggregate analyses are saved to your account; review text is not uploaded.`
                );
            }

            window.dispatchEvent(new CustomEvent('sentiverse:auth-state-changed', { detail: { user: currentUser } }));
        });
    } catch (error) {
        console.error('Supabase client could not be initialized.', error);
        setAuthStatus('Supabase could not be initialized. Check the project URL, anon key, and network connection.', true);
    } finally {
        window.dispatchEvent(new CustomEvent('sentiverse:cloud-ready'));
    }
}

initializeCloudServices();
