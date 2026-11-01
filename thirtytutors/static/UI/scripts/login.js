// ThirtyTutors - hosted mode's login page, which doubles as invite sign-up.

const loginForm = document.getElementById('loginForm');
const inviteField = document.getElementById('inviteField');
const inviteInput = document.getElementById('inviteInput');
const emailInput = document.getElementById('emailInput');
const passwordInput = document.getElementById('passwordInput');
const loginError = document.getElementById('loginError');
const loginSubmit = document.getElementById('loginSubmit');
const loginModeBtn = document.getElementById('loginModeBtn');
const loginIntro = document.getElementById('loginIntro');

let registering = false;

function setMode(register) {
  registering = register;
  inviteField.hidden = !register;
  inviteInput.required = register;
  loginSubmit.textContent = register ? 'Create account' : 'Log in';
  loginModeBtn.textContent = register ? 'I already have an account' : 'I have an invite code';
  loginIntro.textContent = register ? 'Create your account with your invite code.' : 'Log in to continue your lessons.';
  passwordInput.autocomplete = register ? 'new-password' : 'current-password';
  loginError.hidden = true;
}

loginModeBtn.addEventListener('click', () => setMode(!registering));

loginForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  loginSubmit.disabled = true;
  loginError.hidden = true;
  const body = { email: emailInput.value, password: passwordInput.value };
  if (registering) body.invite_code = inviteInput.value.trim();
  try {
    const res = await fetch(registering ? '/api/auth/register' : '/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (res.ok) {
      window.location.href = '/home';
      return;
    }
    const data = await res.json().catch(() => ({}));
    loginError.textContent = data.detail || 'Something went wrong - try again.';
  } catch (err) {
    loginError.textContent = 'Could not reach the server - check your connection.';
  }
  loginError.hidden = false;
  loginSubmit.disabled = false;
});
