// ThirtyTutors - learning page's top-bar session switcher: lists this
// profile's conversations so one can be resumed, or a new one started,
// without going through /profiles. Switching reuses the same
// active-conversation endpoint profileDetail.js does, then reloads, so the
// page's normal bootstrap (conversations.js) picks up the new one. New
// sessions go through /avatar-select like everywhere else.

const sessionSwitcherWrap = document.getElementById('sessionSwitcherWrap');
const sessionSwitcherBtn = document.getElementById('sessionSwitcherBtn');
const sessionSwitcherLabel = document.getElementById('sessionSwitcherLabel');
const sessionSwitcherDropdown = document.getElementById('sessionSwitcherDropdown');
const sessionSwitcherList = document.getElementById('sessionSwitcherList');
const sessionSwitcherStatus = document.getElementById('sessionSwitcherStatus');
const sessionSwitcherNewBtn = document.getElementById('sessionSwitcherNewBtn');

let sessionScenarioLabels = null;

function conversationDisplayName(conv) {
  return conv.name || conv.config?.target_language || 'Session';
}

// Called by conversations.js's selectConversation once a conversation loads.
function updateSessionSwitcherLabel(conv) {
  const name = conversationDisplayName(conv);
  sessionSwitcherLabel.textContent = name;
  sessionSwitcherBtn.title = `Current session: ${name}`;
}

async function fetchScenarioLabels() {
  if (sessionScenarioLabels) return sessionScenarioLabels;
  const res = await fetch('/api/scenarios');
  if (!res.ok) return {};
  const data = await res.json();
  sessionScenarioLabels = Object.fromEntries((data.scenarios || []).map((s) => [s.id, s.label]));
  return sessionScenarioLabels;
}

function sessionMetaText(conv, scenarioLabels) {
  const parts = [];
  const scenario = scenarioLabels[conv.config?.scenario];
  // Names from /avatar-select already include the scenario - see buildName there.
  if (scenario && !conversationDisplayName(conv).includes(scenario)) parts.push(scenario);
  const date = conv.updated_at ? new Date(conv.updated_at) : null;
  if (date && !Number.isNaN(date.getTime())) {
    parts.push(date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }));
  }
  return parts.join(' · ');
}

async function switchToSession(conversationId) {
  if (conversationId === currentConversationId) {
    closeSessionSwitcher();
    return;
  }
  sessionSwitcherStatus.hidden = true;
  const res = await fetch(`/api/profiles/${currentProfile.id}/active-conversation`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId }),
  }).catch(() => null);
  if (!res || !res.ok) {
    sessionSwitcherStatus.textContent = "Couldn't switch sessions - try again.";
    sessionSwitcherStatus.hidden = false;
    return;
  }
  window.location.href = '/';
}

function renderSessionRows(conversations, scenarioLabels) {
  sessionSwitcherList.innerHTML = '';
  const sorted = [...conversations].sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
  sorted.forEach((conv) => {
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'session-switcher-row';
    if (conv.id === currentConversationId) {
      row.classList.add('active');
      row.setAttribute('aria-current', 'true');
    }

    const name = document.createElement('span');
    name.className = 'session-switcher-name';
    name.textContent = conversationDisplayName(conv);
    row.appendChild(name);

    const metaText = sessionMetaText(conv, scenarioLabels);
    if (metaText) {
      const meta = document.createElement('span');
      meta.className = 'session-switcher-meta';
      meta.textContent = metaText;
      row.appendChild(meta);
    }

    row.addEventListener('click', () => switchToSession(conv.id));
    sessionSwitcherList.appendChild(row);
  });
}

function closeSessionSwitcher() {
  sessionSwitcherDropdown.classList.remove('visible');
  sessionSwitcherBtn.setAttribute('aria-expanded', 'false');
}

async function openSessionSwitcher() {
  if (!currentProfile) return;
  sessionSwitcherStatus.hidden = true;
  sessionSwitcherDropdown.classList.add('visible');
  sessionSwitcherBtn.setAttribute('aria-expanded', 'true');
  try {
    const [data, scenarioLabels] = await Promise.all([fetchConversationList(currentProfile.id), fetchScenarioLabels()]);
    renderSessionRows(data.conversations || [], scenarioLabels);
  } catch (e) {
    console.error(e);
    sessionSwitcherStatus.textContent = "Couldn't load your sessions.";
    sessionSwitcherStatus.hidden = false;
  }
}

sessionSwitcherBtn.addEventListener('click', () => {
  if (sessionSwitcherDropdown.classList.contains('visible')) closeSessionSwitcher();
  else openSessionSwitcher();
});
document.addEventListener('click', (e) => {
  if (!sessionSwitcherWrap.contains(e.target)) closeSessionSwitcher();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeSessionSwitcher();
});
sessionSwitcherNewBtn.addEventListener('click', () => {
  if (!currentProfile) return;
  window.location.href = `/avatar-select?profile_id=${encodeURIComponent(currentProfile.id)}&from=home`;
});
