// ThirtyTutors - hosted mode's installable-app behaviour (see _pwa_head.html
// and sw.js): service worker registration, a browser bar that matches the
// theme, the dashboard's install card, and keeping the screen on in a lesson.

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch((e) => console.error(e));
}

// --- Browser/status bar colour ---

const themeColorMeta = document.querySelector('meta[name="theme-color"]');

function syncThemeColor() {
  const panel = getComputedStyle(document.documentElement).getPropertyValue('--panel').trim();
  if (themeColorMeta && panel) themeColorMeta.content = panel;
}
syncThemeColor();
new MutationObserver(syncThemeColor).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', syncThemeColor);

// --- Install card (dashboard only) ---
// Android offers a real install prompt. iOS has none, so the card explains
// the Share menu instead.

const INSTALL_DISMISSED_KEY = 'pwaInstallDismissed';
const homeInstallCard = document.getElementById('homeInstallCard');

function installWasDismissed() {
  try { return localStorage.getItem(INSTALL_DISMISSED_KEY) === '1'; } catch (e) { return false; }
}

function isInstalledApp() {
  return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
}

function isIos() {
  return /iphone|ipad|ipod/i.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

if (homeInstallCard && !installWasDismissed() && !isInstalledApp()) {
  const installBtn = document.getElementById('homeInstallBtn');
  const installText = document.getElementById('homeInstallText');
  let installPrompt = null;

  document.getElementById('homeInstallDismissBtn').addEventListener('click', () => {
    homeInstallCard.hidden = true;
    try { localStorage.setItem(INSTALL_DISMISSED_KEY, '1'); } catch (e) {}
  });

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    installPrompt = e;
    installBtn.hidden = false;
    homeInstallCard.hidden = false;
  });

  installBtn.addEventListener('click', async () => {
    if (!installPrompt) return;
    installPrompt.prompt();
    await installPrompt.userChoice;
    installPrompt = null;
    homeInstallCard.hidden = true;
  });

  window.addEventListener('appinstalled', () => { homeInstallCard.hidden = true; });

  if (isIos()) {
    installText.textContent = 'Tap Share, then Add to Home Screen, to open your lessons like an app.';
    homeInstallCard.hidden = false;
  }
}

// --- Screen stays on during a lesson ---
// A locked phone cuts the microphone. The browser drops the lock whenever the
// page is hidden, so it's requested again on return.

if ('wakeLock' in navigator && document.getElementById('talkBtn')) {
  const requestWakeLock = () => navigator.wakeLock.request('screen').catch(() => {});
  requestWakeLock();
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') requestWakeLock();
  });
}
