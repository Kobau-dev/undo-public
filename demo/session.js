// Realistic session timeout for the demo pages. Hidden controls (not visible in the video):
//   Ctrl+Shift+E  expire the session now      Ctrl+Shift+R  reset the page
//   ?t=90         session length in seconds (default 15 min)
(function () {
  const len = +(new URLSearchParams(location.search).get('t') || 900);
  let left = len, timer = null;
  const el = document.getElementById('session');
  const fmt = (n) => `${Math.floor(n / 60)}:${String(n % 60).padStart(2, '0')}`;
  const fields = () => [...document.querySelectorAll('form input[type=text], form input[type=email], form textarea, form select')];
  function show(cls, text) { const a = document.getElementById('alert'); a.className = `alert show ${cls}`; a.textContent = text; }
  function expire() {
    clearInterval(timer); fields().forEach((f) => (f.value = ''));
    if (el) el.textContent = 'Déconnecté';
    show('error', window.EXPIRED_TEXT || 'Votre session a expiré. Pour votre sécurité, les informations saisies ont été effacées.');
    window.scrollTo(0, 0);
  }
  function start() { clearInterval(timer); left = len; if (el) el.textContent = `Session ${fmt(left)}`; timer = setInterval(() => { left -= 1; if (el) el.textContent = `Session ${fmt(left)}`; if (left <= 0) expire(); }, 1000); }
  window.resetPage = function () { fields().forEach((f) => (f.value = '')); document.getElementById('alert').className = 'alert'; if (window.onReset) window.onReset(); start(); };
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.code === 'KeyE') { e.preventDefault(); expire(); }
    if (e.ctrlKey && e.shiftKey && e.code === 'KeyR') { e.preventDefault(); window.resetPage(); }
  });
  const form = document.querySelector('form');
  if (form) form.addEventListener('submit', (e) => {
    e.preventDefault();
    const missing = fields().filter((f) => !f.value.trim());
    if (missing.length) return show('error', `Merci de compléter : ${missing.map((f) => f.dataset.label || f.name).join(', ')}.`);
    clearInterval(timer); show('ok', window.SENT_TEXT || 'Envoyé.');
  });
  start();
})();
