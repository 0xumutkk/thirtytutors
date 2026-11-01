// ThirtyTutors - global top-bar profile menu (index.html - present on every
// page). Owns `currentProfile` identity for pages that don't load the
// learning page's fuller state.js/profiles.js bootstrap, and the
// profile-menu button + its dropdown (Settings, Switch profile).
//
// currentProfile/conversationsCache/currentConversationId used to be
// declared in state.js (learning-page only). They're declared here now,
// since the profile-menu button and the Settings modal (settings.js,
// also now global) both need currentProfile on every page, not just the
// learning page. conversationsCache/currentConversationId stay at their
// empty defaults everywhere except the learning page, where
// conversations.js populates them exactly as before - see settings.js's
// own header comment for what that means for its Learning/Data-controls
// panes on other pages.
//
// The learning page's init.js/profiles.js still do their own, richer
// profile bootstrap (loading the conversation list, connecting the
// websocket, etc.) via applyProfile() in profiles.js - this file's
// initProfileMenu() below is a lighter, independent fetch that runs
// there too, but the two don't conflict: both just assign the same
// shared `currentProfile` variable, and whichever finishes last wins,
// which is harmless since they fetch the identical record.

let currentProfile = null;
let conversationsCache = [];
let currentConversationId = null;

async function fetchProfile(id) {
  const res = await fetch(`/api/profiles/${id}`);
  if (!res.ok) throw new Error('Profile not found');
  return res.json();
}

const profileMenuBtn = document.getElementById('profileMenuBtn');
const profileMenuDropdown = document.getElementById('profileMenuDropdown');
const profileMenuSettingsBtn = document.getElementById('profileMenuSettingsBtn');
const profileMenuSwitchBtn = document.getElementById('profileMenuSwitchBtn');

function refreshProfileMenuButton() {
  if (currentProfile) {
    profileMenuBtn.textContent = (currentProfile.name[0] || '?').toUpperCase();
    profileMenuBtn.title = currentProfile.name;
    profileMenuBtn.classList.remove('profile-menu-btn-login');
  } else {
    profileMenuBtn.textContent = 'Login';
    profileMenuBtn.title = 'Log in';
    profileMenuBtn.classList.add('profile-menu-btn-login');
  }
}

function closeProfileMenuDropdown() {
  profileMenuDropdown.classList.remove('visible');
}

profileMenuBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  if (!currentProfile) {
    // No profile logged in - this is a plain link, not a dropdown (there's
    // nothing to open Settings onto without a profile). /profiles is where
    // an existing profile is picked or a new one is started (via its own
    // "Add profile" tile, which hands off to /get-started).
    window.location.href = '/profiles';
    return;
  }
  profileMenuDropdown.classList.toggle('visible');
  // Forces an immediate repaint - a display:none -> block/flex change on an
  // overlay or dropdown was observed not actually painting until some
  // UNRELATED event forced the browser to recomposite the page: a
  // paint-timing glitch, not a CSS logic bug (every computed style was
  // already correct beforehand). Reading a layout property synchronously
  // makes it happen now. Same fix in notes.js/settings.js/update.js.
  void profileMenuDropdown.offsetHeight;
});
document.addEventListener('click', (e) => {
  if (!profileMenuDropdown.contains(e.target) && e.target !== profileMenuBtn) closeProfileMenuDropdown();
});

profileMenuSettingsBtn.addEventListener('click', () => {
  closeProfileMenuDropdown();
  if (typeof openSettingsModal === 'function') openSettingsModal();
});

profileMenuSwitchBtn.addEventListener('click', () => {
  closeProfileMenuDropdown();
  window.location.href = '/profiles';
});

// Hosted mode only - the desktop app has no accounts (see auth.py).
const profileMenuLogoutBtn = document.getElementById('profileMenuLogoutBtn');

profileMenuLogoutBtn.addEventListener('click', async () => {
  await fetch('/api/auth/logout', { method: 'POST' }).catch(() => {});
  try { localStorage.removeItem('tutorProfileId'); } catch (e) {}
  window.location.href = '/login';
});

fetch('/api/auth/me')
  .then((res) => res.json())
  .then((me) => { profileMenuLogoutBtn.hidden = !me.hosted; })
  .catch(() => {});

async function initProfileMenu() {
  const savedId = localStorage.getItem('tutorProfileId');
  if (!savedId) {
    refreshProfileMenuButton();
    return;
  }
  try {
    currentProfile = await fetchProfile(savedId);
  } catch (e) {
    currentProfile = null;
    localStorage.removeItem('tutorProfileId');
  }
  refreshProfileMenuButton();
}
initProfileMenu();
