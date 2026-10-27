// Paths are relative to this module so / and /app/ load the same application.
const asset = path => new URL(path, import.meta.url).href;
const status = document.getElementById('startup');
const detail = document.getElementById('startup-detail');
const started = Date.now();
let failed = false;
function fail() {
  failed = true;
  status.hidden = false;
  status.classList.add('error');
  detail.textContent = 'Unable to start the app. Check your connection and reload. If the problem persists, review the error below or follow the documentation to run locally.';
}
const timer = setInterval(() => {
  const app = document.querySelector('[data-testid="stSidebar"]');
  if (app) { status.hidden = true; clearInterval(timer); return; }
  if (failed) return;
  if (document.querySelector('[data-testid="stException"]')) { fail(); return; }
  const seconds = Math.floor((Date.now() - started) / 1000);
  const progress = [...document.querySelectorAll('[role="status"]')]
    .filter(node => !status.contains(node)).map(node => node.textContent.trim()).filter(Boolean).join(' · ');
  detail.textContent = `Downloading the Python runtime and analysis packages (${seconds}s elapsed). Please keep this page open.${progress ? ' ' + progress : ''}`;
  if (seconds > 180) detail.textContent += ' Loading is taking longer than expected. You can keep waiting or reload to retry.';
}, 1000);
try {
  const response = await fetch(asset('vendor/requirements.json'));
  if (!response.ok) throw new Error('Missing runtime dependencies');
  const wheels = await response.json();
  const {mount} = await import('./vendor/stlite/stlite.js');
  mount({
    entrypoint: 'app.py',
    pyodideUrl: asset('vendor/pyodide/pyodide.js'),
    wheelUrls: {
      streamlit: asset('vendor/stlite/wheels/streamlit-1.45.1-cp312-none-any.whl'),
      stliteLib: asset('vendor/stlite/wheels/stlite_lib-0.1.0-py3-none-any.whl')
    },
    prebuiltPackageNames: ['numpy','matplotlib','requests','sqlite3','pandas','altair','cachetools','protobuf','typing-extensions','pyodide-http','fastparquet'],
    requirements: wheels.map(asset),
    archives: [{url: asset('runtime.zip?v=20261026-selfhost'), format: 'zip'}],
    idbfsMountpoints: ['/ts2r-data'],
    streamlitConfig: {
      'client.toolbarMode': 'viewer',
      'theme.primaryColor': '#245b46',
      'theme.backgroundColor': '#ffffff',
      'theme.secondaryBackgroundColor': '#f2f5ee',
      'theme.textColor': '#16332d'
    }
  }, document.getElementById('root'));
} catch (error) {
  console.error('Application startup failed', error);
  fail();
  clearInterval(timer);
}
