document.addEventListener('DOMContentLoaded', () => {
  const currentPage = window.location.pathname.split('/').pop() || 'index.html';

  document.querySelectorAll('.nav-link').forEach((link) => {
    const href = link.getAttribute('href');
    if (href === currentPage || (currentPage === '' && href === 'index.html')) {
      link.classList.add('active');
    }
  });

  const authTabs = document.querySelectorAll('[data-auth-tab]');
  const authForm = document.getElementById('auth-form');
  authTabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      const targetMode = tab.dataset.authTab;
      authTabs.forEach((item) => item.classList.toggle('active', item === tab));
      if (authForm) {
        authForm.dataset.mode = targetMode;
        const submitText = targetMode === 'signup' ? 'Create account' : 'Log in';
        const submitButton = authForm.querySelector('button[type="submit"]');
        if (submitButton) submitButton.textContent = submitText;
      }
      const nameGroup = document.getElementById('name-group');
      if (nameGroup) {
        const isSignup = targetMode === 'signup';
        nameGroup.classList.toggle('hidden', !isSignup);
        const nameInput = nameGroup.querySelector('input');
        if (nameInput) nameInput.required = isSignup;
      }
    });
  });
});
