// ThirtyTutors - personal dashboard (/home), the logged-in counterpart to
// the marketing /landing page: progress numbers, this profile's sessions,
// and its details. Read-only over the same endpoints the Settings modal's
// Stats tab and the session switcher already use - language cards and the
// hours format are statsPane.js's own, which index.html loads on every page.

const homeGreeting = document.getElementById('homeGreeting');
const homeResumeText = document.getElementById('homeResumeText');
const homeContinueBtn = document.getElementById('homeContinueBtn');
const homeNewSessionBtn = document.getElementById('homeNewSessionBtn');
const homeStatus = document.getElementById('homeStatus');
const homeStreakValue = document.getElementById('homeStreakValue');
const homeHoursValue = document.getElementById('homeHoursValue');
const homeSessionsValue = document.getElementById('homeSessionsValue');
const homeWordsValue = document.getElementById('homeWordsValue');
const homeReviewReminder = document.getElementById('homeReviewReminder');
const homeSessionList = document.getElementById('homeSessionList');
const homeProfileInfo = document.getElementById('homeProfileInfo');
const homeEditProfileBtn = document.getElementById('homeEditProfileBtn');
const homeLanguageList = document.getElementById('homeLanguageList');

function homeShowError(message) {
  homeStatus.textContent = message;
  homeStatus.hidden = false;
}

function homeSessionName(conv) {
  return conv.name || conv.config?.target_language || 'Session';
}

function homeSessionMeta(conv, scenarioLabels) {
  const parts = [];
  const scenario = scenarioLabels[conv.config?.scenario];
  // Names from /avatar-select already include the scenario - see buildName there.
  if (scenario && !homeSessionName(conv).includes(scenario)) parts.push(scenario);
  const date = conv.updated_at ? new Date(conv.updated_at) : null;
  if (date && !Number.isNaN(date.getTime())) {
    parts.push(date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }));
  }
  return parts.join(' · ');
}

// Same active-conversation switch as sessionSwitcher.js/profileDetail.js -
// the learning page's normal bootstrap then picks it up.
async function homeOpenSession(profileId, conversationId) {
  homeStatus.hidden = true;
  const res = await fetch(`/api/profiles/${profileId}/active-conversation`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId }),
  }).catch(() => null);
  if (!res || !res.ok) {
    homeShowError("Couldn't open that session - try again.");
    return;
  }
  window.location.href = '/';
}

function homeBuildSessionRow(profile, conv, isActive, scenarioLabels) {
  const row = document.createElement('div');
  row.className = 'home-session-row';

  const name = homeSessionName(conv);
  const openBtn = document.createElement('button');
  openBtn.type = 'button';
  openBtn.className = 'home-session-open';
  openBtn.addEventListener('click', () => homeOpenSession(profile.id, conv.id));

  const title = document.createElement('span');
  title.className = 'home-session-name';
  title.textContent = name;
  openBtn.appendChild(title);

  const metaText = homeSessionMeta(conv, scenarioLabels);
  if (metaText) {
    const meta = document.createElement('span');
    meta.className = 'home-session-meta';
    meta.textContent = metaText;
    openBtn.appendChild(meta);
  }
  row.appendChild(openBtn);

  if (isActive) {
    row.classList.add('active');
    const badge = document.createElement('span');
    badge.className = 'home-session-badge';
    badge.textContent = 'Current';
    row.appendChild(badge);
  }

  const notesBtn = document.createElement('button');
  notesBtn.type = 'button';
  notesBtn.className = 'icon-btn';
  notesBtn.title = 'View notes';
  notesBtn.setAttribute('aria-label', `View notes for ${name}`);
  notesBtn.textContent = '📝';
  notesBtn.addEventListener('click', () => openNotesModal(profile.id, conv.id, name));
  row.appendChild(notesBtn);

  const quizBtn = document.createElement('a');
  quizBtn.className = 'icon-btn';
  quizBtn.title = 'Test yourself';
  quizBtn.setAttribute('aria-label', `Test yourself on ${name}`);
  quizBtn.textContent = '🧩';
  quizBtn.href = `/quiz-mode?profile_id=${encodeURIComponent(profile.id)}&conversation_id=${encodeURIComponent(conv.id)}`;
  row.appendChild(quizBtn);

  return row;
}

function homeRenderSessions(profile, conversations, activeId, scenarioLabels) {
  const sorted = [...conversations].sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
  const resume = sorted.find((c) => c.id === activeId) || sorted[0];

  homeSessionList.innerHTML = '';
  if (!resume) {
    homeResumeText.textContent = 'Start your first session to see your progress here.';
    const empty = document.createElement('p');
    empty.className = 'field-hint';
    empty.textContent = 'No sessions yet.';
    homeSessionList.appendChild(empty);
    return;
  }

  homeResumeText.textContent = `Pick up where you left off: ${homeSessionName(resume)}`;
  homeContinueBtn.hidden = false;
  homeContinueBtn.addEventListener('click', () => homeOpenSession(profile.id, resume.id));
  sorted.forEach((conv) => {
    homeSessionList.appendChild(homeBuildSessionRow(profile, conv, conv.id === resume.id, scenarioLabels));
  });
}

function homeRenderStats(stats) {
  homeStreakValue.textContent = String(stats.current_streak || 0);
  homeHoursValue.textContent = formatStudyHours(stats.total_seconds_studied || 0);
  homeSessionsValue.textContent = String(stats.conversations_total || 0);
  homeWordsValue.textContent = String((stats.languages || []).reduce((sum, b) => sum + b.vocab_mastered, 0));

  const reviewCount = stats.review_candidates_total || 0;
  homeReviewReminder.hidden = reviewCount === 0;
  homeReviewReminder.textContent = `${reviewCount} word${reviewCount === 1 ? '' : 's'} ready for review - use 🧩 on a session to test yourself.`;

  homeLanguageList.innerHTML = '';
  if (!stats.languages || stats.languages.length === 0) {
    const empty = document.createElement('p');
    empty.className = 'field-hint';
    empty.textContent = 'Start a session to see your languages here.';
    homeLanguageList.appendChild(empty);
    return;
  }
  stats.languages.forEach((bucket) => homeLanguageList.appendChild(buildLanguageCard(bucket)));
}

// Deliberately says only whether an API key is set - the key itself never
// gets rendered on a page that's on screen every launch.
function homeRenderProfile(profile) {
  const rows = [
    ['Name', profile.name],
    ['Native language', profile.native_language],
    ['Default level', profile.default_difficulty && profile.default_difficulty[0].toUpperCase() + profile.default_difficulty.slice(1)],
    ['Microphone', profile.mic_label || 'Default microphone'],
    ['Gemini API key', profile.api_key ? 'Added' : 'Not added'],
  ];
  homeProfileInfo.innerHTML = '';
  rows.forEach(([label, value]) => {
    if (!value) return;
    const dt = document.createElement('dt');
    dt.textContent = label;
    const dd = document.createElement('dd');
    dd.textContent = value;
    homeProfileInfo.append(dt, dd);
  });
}

async function homeFetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function initHome() {
  const savedId = localStorage.getItem('tutorProfileId');
  if (!savedId) {
    window.location.replace('/landing');
    return;
  }

  let profile;
  try {
    profile = await fetchProfile(savedId);
  } catch (e) {
    // Cleared here rather than left to profileMenu.js's identical fetch,
    // which may not finish first - /landing bounces back here while the id
    // is still set.
    localStorage.removeItem('tutorProfileId');
    window.location.replace('/landing');
    return;
  }

  homeGreeting.textContent = `Welcome back, ${profile.name}`;
  homeRenderProfile(profile);
  homeNewSessionBtn.addEventListener('click', () => {
    window.location.href = `/avatar-select?profile_id=${encodeURIComponent(profile.id)}&from=dashboard`;
  });
  homeEditProfileBtn.addEventListener('click', () => {
    if (typeof openSettingsModal === 'function') openSettingsModal();
  });

  // Each section loads on its own, so one failing still leaves the other usable.
  homeFetchJson(`/api/profiles/${profile.id}/stats`)
    .then(homeRenderStats)
    .catch((e) => {
      console.error(e);
      homeShowError("Couldn't load your progress.");
    });

  try {
    const [conversationData, scenarioData] = await Promise.all([
      homeFetchJson(`/api/profiles/${profile.id}/conversations`),
      homeFetchJson('/api/scenarios').catch(() => ({})),
    ]);
    const scenarioLabels = Object.fromEntries((scenarioData.scenarios || []).map((s) => [s.id, s.label]));
    homeRenderSessions(profile, conversationData.conversations || [], conversationData.active_conversation_id, scenarioLabels);
  } catch (e) {
    console.error(e);
    homeResumeText.textContent = '';
    homeShowError("Couldn't load your sessions.");
  }
}

initHome();
