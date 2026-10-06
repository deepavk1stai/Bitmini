const DEFAULT_STATE = {
  currentView: 'home',
  lastView: 'home',
  balance: 0,
  stakedBalance: 0,
  slashedTotal: 0,
  price: 35,
  fiatValue: 0,
  walletAddress: 'B8N9xZQ7v4h3mt2v8k1c6f0p9d3q7r4w',
  userCategory: 'consumer',
  userCategories: ['consumer'],
  referralCode: '',
  referralEarnings: 0,
  consensusMode: 'pos',
  consensusLabel: 'Proof of Stake',
  consensusProfiles: {},
  epoch: 1,
  epochLength: 3,
  selectedValidators: [],
  adminSnapshot: null,
  referralSnapshot: null,
  adsSnapshot: null,
  leaderboardSnapshot: null,
  recentNetworkTransactions: [],
  alerts: [
    { label: 'Price alert: $34,000', status: 'Activated', value: '+3.2%' },
    { label: '10% movement alert', status: 'Watching', value: '+2.1%' },
    { label: 'Portfolio value target', status: 'Ready', value: '+6.5%' }
  ],
  transactions: [
    { type: 'Genesis', value: '+0.0000', amount: '+$0.00', note: 'Wallet created', time: 'Just now', positive: true }
  ],
  contacts: [
    { name: 'Aster Labs', address: 'B8N9...9d4f', tag: 'Trusted' },
    { name: 'Smith Holdings', address: 'B12A...e2cd', tag: 'Business' },
    { name: 'Luna Pay', address: 'B4c0...11ae', tag: 'Merchant' }
  ]
};

const state = { ...DEFAULT_STATE };
const auth = {
  sessionToken: localStorage.getItem('bitminiSessionToken') || '',
  walletAddress: localStorage.getItem('bitminiWalletAddress') || ''
};

const params = new URLSearchParams(window.location.search);
if (params.get('session')) {
  auth.sessionToken = params.get('session');
  localStorage.setItem('bitminiSessionToken', auth.sessionToken);
}
if (params.get('wallet')) {
  auth.walletAddress = params.get('wallet');
  localStorage.setItem('bitminiWalletAddress', auth.walletAddress);
}

const navLabels = {
  home: 'Bitmini Wallet',
  wallet: 'Wallet Overview',
  register: 'Register Wallet',
  mine: 'Mobile Validation',
  send: 'Send Bitmini',
  receive: 'Receive Bitmini',
  'buy-sell': 'Buy / Sell',
  activity: 'Transaction Activity',
  markets: 'Market Explorer',
  ads: 'Ads Marketplace',
  contacts: 'Contacts',
  referrals: 'Referral Rewards',
  leaderboards: 'Top Referral Earners',
  transactions: 'Last 10 Transactions',
  admin: 'Admin Monitor',
  settings: 'Security & Settings'
};

async function readJsonSafe(response) {
  try {
    return await response.json();
  } catch (error) {
    return null;
  }
}

async function loadWalletData() {
  try {
    const walletUrl = auth.walletAddress
      ? `/api/wallet?address=${encodeURIComponent(auth.walletAddress)}`
      : '/api/wallet';
    const [walletResponse, consensusResponse, epochResponse, adminResponse, networkHealthResponse, networkMetricsResponse, leaderboardResponse, recentTxResponse] = await Promise.all([
      fetch(walletUrl),
      fetch('/api/consensus'),
      fetch('/api/epoch'),
      fetch('/api/admin'),
      fetch('/api/network/health'),
      fetch('/api/network/token-metrics'),
      fetch('/api/leaderboards?limit=10'),
      fetch('/api/transactions/recent?limit=10')
    ]);
    if (!walletResponse.ok) {
      if (auth.walletAddress && walletUrl !== '/api/wallet') {
        auth.walletAddress = '';
        localStorage.removeItem('bitminiWalletAddress');
        return loadWalletData();
      }
      throw new Error('Wallet fetch failed');
    }
    const wallet = await walletResponse.json();
    Object.assign(state, DEFAULT_STATE, wallet);
    if (state.walletAddress) {
      auth.walletAddress = state.walletAddress;
      localStorage.setItem('bitminiWalletAddress', state.walletAddress);
    }
    const referralResponse = await fetch(`/api/referrals?address=${encodeURIComponent(state.walletAddress)}`);
    if (referralResponse.ok) {
      state.referralSnapshot = await referralResponse.json();
    }
    const adsResponse = await fetch(`/api/ads/market?address=${encodeURIComponent(state.walletAddress)}`, { headers: authedHeaders() });
    if (adsResponse.ok) {
      state.adsSnapshot = await adsResponse.json();
    }
    if (consensusResponse.ok) {
      const consensusData = await consensusResponse.json();
      state.consensusProfiles = consensusData.profiles || {};
    }
    if (epochResponse.ok) {
      const epochData = await epochResponse.json();
      state.epoch = epochData.epoch || 1;
      state.epochLength = epochData.epochLength || 3;
      state.selectedValidators = epochData.selectedValidators || [];
    }
    if (leaderboardResponse.ok) {
      state.leaderboardSnapshot = await leaderboardResponse.json();
    }
    if (recentTxResponse.ok) {
      const txPayload = await recentTxResponse.json();
      state.recentNetworkTransactions = Array.isArray(txPayload.transactions) ? txPayload.transactions : [];
    }
    const networkHealth = await readJsonSafe(networkHealthResponse);
    const networkMetrics = await readJsonSafe(networkMetricsResponse);

    if (adminResponse.ok) {
      state.adminSnapshot = await adminResponse.json();
      state.adminSnapshot.networkNode = {
        health: networkHealth,
        tokenMetrics: networkMetrics
      };
    }
    state.currentView = state.currentView || 'home';
    renderView();
  } catch (error) {
    console.error(error);
    renderView();
  }
}

function authedHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (auth.sessionToken) {
    headers['X-Bitmini-Session'] = auth.sessionToken;
  }
  return headers;
}

function formatBmini(value) {
  return `${Number(value).toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 4 })} BMINI`;
}

function formatUsd(value) {
  return `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function createQrMarkup() {
  const cells = [];
  for (let row = 0; row < 9; row += 1) {
    for (let col = 0; col < 9; col += 1) {
      const dark =
        (row < 3 && col < 3) ||
        (row < 3 && col > 5) ||
        (row > 5 && col < 3) ||
        (row > 5 && col > 5) ||
        ((row + col) % 2 === 0 && row > 2 && row < 6 && col > 2 && col < 6) ||
        (row === 4 && col === 4) ||
        (row === 2 && col === 6) ||
        (row === 6 && col === 2);
      cells.push(`<span class="${dark ? 'dark' : ''}"></span>`);
    }
  }
  return cells.join('');
}

function renderRealQrCode(target, value) {
  if (!target) {
    return;
  }

  const safeValue = encodeURIComponent(value || 'bitmini:wallet');
  const img = document.createElement('img');
  img.src = `/api/qr?value=${safeValue}`;
  img.alt = 'Bitmini payment QR code';
  img.className = 'qr-image';
  img.style.width = '100%';
  img.style.height = '100%';
  img.style.maxWidth = '100%';
  img.style.maxHeight = '100%';
  img.style.objectFit = 'contain';
  img.style.borderRadius = '18px';
  img.style.background = '#ffffff';
  img.style.boxShadow = '0 12px 24px rgba(9, 33, 46, 0.08)';
  target.innerHTML = '';
  target.appendChild(img);
}

function renderTransactions(items = state.transactions) {
  if (!items.length) return '<div class="empty-state">No transactions yet. Your genesis block is waiting.</div>';
  return items.map((item) => {
    const valueClass = item.positive ? 'positive' : 'negative';
    const icon = item.type === 'Received' ? 'R' : item.type === 'Sent' ? 'S' : item.type === 'Bought' ? 'B' : item.type === 'Sold' ? 'O' : 'G';
    return `
      <div class="transaction-item">
        <div class="tx-info">
          <div class="tx-icon">${icon}</div>
          <div class="tx-meta">
            <strong>${item.type}</strong>
            <span>${item.note} · ${item.time}</span>
          </div>
        </div>
        <div class="tx-value ${valueClass}">${item.value}<br /><span>${item.amount}</span></div>
      </div>
    `;
  }).join('');
}

function renderAlerts() {
  return state.alerts.map((item) => `
    <li class="alert-item">
      <div>
        <strong>${item.label}</strong>
        <span>${item.status}</span>
      </div>
      <span class="delta positive">${item.value}</span>
    </li>
  `).join('');
}

function renderHome() {
  return `
    <section class="overview-grid">
      <article class="hero-card wallet-card">
        <div class="pill-row">
          <span class="status-pill success">Genesis block</span>
          <span class="status-pill neutral">Verified</span>
        </div>
        <div class="balance-block">
          <p class="eyebrow muted">Available balance</p>
          <h3>${formatBmini(state.balance)}</h3>
          <p class="fiat-value">≈ ${formatUsd(state.fiatValue)} USD</p>
        </div>
        <div class="mini-metrics">
          <div>
            <span>Confirmed</span>
            <strong>${formatBmini(state.balance)}</strong>
          </div>
          <div>
            <span>Pending</span>
            <strong>0.0000</strong>
          </div>
          <div>
            <span>Fiat</span>
            <strong>${formatUsd(state.fiatValue)}</strong>
          </div>
        </div>
      </article>

      <article class="panel price-card">
        <div class="panel-header">
          <div>
            <p class="eyebrow muted">Price</p>
            <h3>BMINI / USD</h3>
          </div>
          <span class="delta positive">+8.32%</span>
        </div>
        <div class="price-row">
          <strong>${formatUsd(state.price)}</strong>
          <span>Genesis market data</span>
        </div>
        <div class="sparkline" aria-hidden="true">
          <span style="height: 22%"></span>
          <span style="height: 28%"></span>
          <span style="height: 25%"></span>
          <span style="height: 36%"></span>
          <span style="height: 44%"></span>
          <span style="height: 38%"></span>
          <span style="height: 50%"></span>
          <span style="height: 56%"></span>
          <span style="height: 52%"></span>
          <span style="height: 60%"></span>
          <span style="height: 58%"></span>
          <span style="height: 64%"></span>
        </div>
      </article>
    </section>

    <section class="quick-actions" aria-label="Quick actions">
      <button class="action-button primary" data-view="send">Send</button>
      <button class="action-button" data-view="receive">Receive</button>
      <button class="action-button" data-view="buy-sell">Buy</button>
      <button class="action-button" data-view="markets">Sell</button>
    </section>

    <section class="content-grid">
      <article class="panel transaction-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow muted">Recent activity</p>
            <h3>Transactions</h3>
          </div>
          <button class="text-button" data-view="activity">View all</button>
        </div>
        <div class="transaction-list">${renderTransactions()}</div>
      </article>

      <article class="panel send-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow muted">Transfer</p>
            <h3>Send Bitmini</h3>
          </div>
        </div>
        <form id="sendForm" class="send-form">
          <label> Recipient address <input id="recipient" type="text" value="B8N9xZ...a32f7" /> </label>
          <div class="split-row">
            <label> Amount <input id="amount" type="number" step="0.0001" min="0" value="0" /> </label>
            <label> Fee <input type="text" value="0.0000" readonly /> </label>
          </div>
          <label> Optional note <input id="note" type="text" value="Client payment" /> </label>
          <div class="split-row">
            <label> Security method
              <select id="sendSecurityMethod">
                <option value="password">Password</option>
                <option value="seed_phrase">Seed phrase</option>
              </select>
            </label>
            <label> Wallet secret <input id="sendSecret" type="password" placeholder="Enter password or seed phrase" required /> </label>
          </div>
          <div class="totals">
            <span>Total</span>
            <strong id="totalAmount">$0.00</strong>
          </div>
          <button class="primary-button full-width" type="submit">Review transfer</button>
        </form>
      </article>
    </section>

    <section class="bottom-grid">
      <article class="panel qr-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow muted">Receive</p>
            <h3>QR payment</h3>
          </div>
        </div>
        <div class="qr-card">
          <div id="qrCode" class="qr-code" aria-label="Bitmini payment QR code"></div>
        </div>
        <div class="address-row">
          <span>${state.walletAddress}</span>
          <button class="small-button" id="copyAddress">Copy</button>
        </div>
      </article>

      <article class="panel alerts-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow muted">Price alerts</p>
            <h3>Monitoring</h3>
          </div>
        </div>
        <ul class="alert-list">${renderAlerts()}</ul>
      </article>

    </section>
  `;
}

function renderWallet() {
  return `
    <section class="stacked-section">
      <article class="panel big-card">
        <div class="panel-header">
          <div>
            <p class="eyebrow muted">Wallet</p>
            <h3>Portfolio overview</h3>
          </div>
          <span class="status-pill success">${state.status || 'Verified'}</span>
        </div>
        <div class="wallet-summary-grid">
          <div><label>Balance</label><strong>${formatBmini(state.balance)}</strong></div>
          <div><label>Fiat value</label><strong>${formatUsd(state.fiatValue)}</strong></div>
          <div><label>Mode</label><strong>${state.mode || 'Self-custody'}</strong></div>
        </div>
      </article>
      <article class="panel">
        <div class="panel-header">
          <div><p class="eyebrow muted">Wallet address</p><h3>Receive address</h3></div>
        </div>
        <div class="address-box">${state.walletAddress}</div>
      </article>
      <article class="panel">
        <div class="panel-header">
          <div><p class="eyebrow muted">Referral</p><h3>Invite friends and earn</h3></div>
        </div>
        <div class="address-box">Code: ${state.referralCode || 'N/A'}</div>
        <div class="totals"><span>Referral earnings</span><strong>${formatBmini(state.referralEarnings || 0)}</strong></div>
        <button class="ghost-button full-width" type="button" id="copyReferralCode">Copy referral code</button>
      </article>
    </section>
  `;
}

function renderRegister() {
  return `
    <section class="panel send-screen">
      <div class="panel-header">
        <div><p class="eyebrow muted">Account</p><h3>Register new wallet</h3></div>
      </div>
      <form id="registerForm" class="send-form large">
        <label> Full name <input id="registerName" type="text" placeholder="Jane Doe" required /> </label>
        <label> Username <input id="registerUsername" type="text" pattern="@[A-Za-z0-9._\-]{3,24}" placeholder="@jane2026" required /> </label>
        <label> Date of birth <input id="registerDob" type="date" required /> </label>
        <label> Zipcode <input id="registerZip" type="text" pattern="[0-9A-Za-z\- ]{3,12}" placeholder="10001" required /> </label>
        <label> Email <input id="registerEmail" type="email" placeholder="jane@example.com" required /> </label>
        <label> Password <input id="registerPassword" type="password" minlength="8" placeholder="At least 8 characters" required /> </label>
        <label> Referral code (optional) <input id="registerReferralCode" type="text" placeholder="RABCDEFG1" /> </label>
        <div class="totals">
          <span>Wallet type</span>
          <strong>Bitmini wallet</strong>
        </div>
        <button class="primary-button full-width" type="submit">Create wallet & download</button>
      </form>
    </section>
  `;
}

function renderMine() {
  const profiles = state.consensusProfiles || {};
  const profileOptions = Object.entries(profiles).map(([key, profile]) => {
    const mobile = profile.mobile_ready ? 'mobile' : 'gpu';
    const selected = key === state.consensusMode ? 'selected' : '';
    return `<option value="${key}" ${selected}>${profile.label} (${mobile}, ${profile.energy})</option>`;
  }).join('');

  return `
    <section class="panel send-screen">
      <div class="panel-header">
        <div><p class="eyebrow muted">Consensus</p><h3>Mobile-friendly validation</h3></div>
      </div>
      <form id="consensusForm" class="send-form large">
        <label> Wallet address <input id="mineWalletAddress" type="text" value="${state.walletAddress}" readonly /> </label>
        <label> Consensus mode
          <select id="consensusModeSelect">
            ${profileOptions}
          </select>
        </label>
        <label> Stake amount to lock <input id="stakeAmount" type="number" min="0" step="0.1" value="0" /> </label>
        <button class="ghost-button full-width" type="button" id="stakeButton">Lock stake</button>
        <label> Slashing reason <input id="slashReason" type="text" value="Test slash event" /> </label>
        <button class="ghost-button full-width" type="button" id="slashButton">Apply slash penalty</button>
        <label> Validation reward target <input id="mineReward" type="number" min="0.1" step="0.1" value="2" /> </label>
        <div class="totals">
          <span>Balances</span>
          <strong>Available ${formatBmini(state.balance)} | Staked ${formatBmini(state.stakedBalance || 0)} | Slashed ${formatBmini(state.slashedTotal || 0)}</strong>
        </div>
        <div class="totals">
          <span>Epoch ${state.epoch} / ${state.epochLength}</span>
          <strong>Selected validators: ${(state.selectedValidators || []).join(', ') || 'None selected yet'}</strong>
        </div>
        <button class="primary-button full-width" type="submit">Validate and earn</button>
      </form>
    </section>
  `;
}

function renderSend() {
  return `
    <section class="panel send-screen">
      <div class="panel-header"><div><p class="eyebrow muted">Transfer</p><h3>Send BMINI</h3></div></div>
      <form id="sendFormPage" class="send-form large">
        <label> Recipient address <input id="pageRecipient" type="text" placeholder="Enter wallet address" /> </label>
        <div class="split-row">
          <label> Amount <input id="pageAmount" type="number" min="0" step="0.0001" value="0" /> </label>
          <label> Fee <input type="text" value="0.0000" readonly /> </label>
        </div>
        <label> Memo <input id="pageMemo" type="text" placeholder="Optional message" /> </label>
        <div class="split-row">
          <label> Security method
            <select id="pageSendSecurityMethod">
              <option value="password">Password</option>
              <option value="seed_phrase">Seed phrase</option>
            </select>
          </label>
          <label> Wallet secret <input id="pageSendSecret" type="password" placeholder="Enter password or seed phrase" required /> </label>
        </div>
        <div class="totals"><span>Total</span><strong id="pageTotal">$0.00</strong></div>
        <button class="primary-button full-width" type="submit">Send now</button>
      </form>
    </section>
  `;
}

function renderReceive() {
  return `
    <section class="panel receive-screen">
      <div class="panel-header"><div><p class="eyebrow muted">Receive</p><h3>Payment request</h3></div></div>
      <div class="receive-layout">
        <div class="qr-card large"><div id="receiveQr" class="qr-code large-qr" aria-label="Bitmini payment QR code"></div></div>
        <div class="receive-info">
          <div class="address-box">${state.walletAddress}</div>
          <div class="inline-actions">
            <button class="small-button" id="copyReceiveAddress">Copy</button>
            <button class="ghost-button" id="shareRequest">Share</button>
          </div>
          <label> Request amount <input type="number" min="0" step="0.0001" value="0" /> </label>
        </div>
      </div>
    </section>
  `;
}

function renderBuySell() {
  return `
    <section class="panel">
      <div class="panel-header"><div><p class="eyebrow muted">On-ramp</p><h3>Buy / Sell</h3></div></div>
      <div class="market-grid">
        <div class="market-card">
          <label>Buy BMINI</label>
          <strong>${formatUsd(state.price)} per coin</strong>
          <p>Real money payment rails are not configured for this deployment. Fiat on-ramp and off-ramp services must be enabled before trading is available.</p>
          <button class="primary-button full-width" type="button" disabled>Buy unavailable</button>
        </div>
        <div class="market-card">
          <label>Sell BMINI</label>
          <strong>Not enabled</strong>
          <span>No fiat withdrawal integration is configured for this environment.</span>
          <button class="ghost-button full-width" type="button" disabled>Sell unavailable</button>
        </div>
      </div>
    </section>
  `;
}

function renderActivity() {
  return `
    <section class="panel"><div class="panel-header"><div><p class="eyebrow muted">History</p><h3>All activity</h3></div></div><div class="transaction-list">${renderTransactions()}</div></section>
  `;
}

function renderMarkets() {
  return `
    <section class="market-grid">
      <article class="panel market-card-wide">
        <div class="panel-header"><div><p class="eyebrow muted">Market</p><h3>Bitmini price board</h3></div></div>
        <div class="price-row big">
          <strong>${formatUsd(state.price)}</strong>
          <span class="delta positive">+8.32%</span>
        </div>
        <div class="sparkline large" aria-hidden="true">
          <span style="height: 20%"></span><span style="height: 34%"></span><span style="height: 30%"></span><span style="height: 46%"></span><span style="height: 51%"></span><span style="height: 64%"></span><span style="height: 72%"></span><span style="height: 69%"></span><span style="height: 80%"></span><span style="height: 76%"></span><span style="height: 90%"></span><span style="height: 100%"></span>
        </div>
      </article>
      <article class="panel market-card-wide">
        <div class="panel-header"><div><p class="eyebrow muted">Monitoring</p><h3>Alerts</h3></div></div>
        <ul class="alert-list">${renderAlerts()}</ul>
      </article>
    </section>
  `;
}

function renderAds() {
  const market = state.adsSnapshot;
  if (!market) {
    return '<section class="panel"><div class="panel-header"><div><p class="eyebrow muted">Ads</p><h3>Marketplace</h3></div></div><p>Ads marketplace data is not available yet.</p></section>';
  }

  const ads = market.ads || [];
  const topSpenders = market.topSpenders || [];
  const myAds = market.myAds || [];

  return `
    <section class="settings-grid">
      <article class="panel">
        <div class="panel-header"><div><p class="eyebrow muted">Sell ads</p><h3>Create ad campaign</h3></div></div>
        <div class="totals"><span>Current category</span><strong>${state.userCategory || 'consumer'}</strong></div>
        <form id="setCategoryForm" class="send-form large" style="margin-top:10px;">
          <label> Wallet category
            <select id="walletCategory" required>
              <option value="consumer" ${(state.userCategory === 'consumer' ? 'selected' : '')}>Consumer</option>
              <option value="validator" ${(state.userCategory === 'validator' ? 'selected' : '')}>Validator</option>
              <option value="promoter" ${(state.userCategory === 'promoter' ? 'selected' : '')}>Promoter</option>
              <option value="advertiser" ${(state.userCategory === 'advertiser' ? 'selected' : '')}>Advertiser</option>
            </select>
          </label>
          <button class="ghost-button full-width" type="submit">Update category</button>
        </form>
        <form id="createAdForm" class="send-form large">
          <label> Ad type
            <select id="adType" required>
              <option value="video">Video link</option>
              <option value="site">Site link</option>
              <option value="poster">Poster</option>
            </select>
          </label>
          <label> Title <input id="adTitle" type="text" minlength="3" placeholder="Campaign title" required /> </label>
          <label> Description <input id="adDescription" type="text" placeholder="Short campaign message" /> </label>
          <label> Media link <input id="adMediaUrl" type="url" placeholder="https://example.com/video-or-poster" /> </label>
          <label> Target site link <input id="adTargetUrl" type="url" placeholder="https://example.com" /> </label>
          <div class="split-row">
            <label> Spend per view (BMINI) <input id="adBidPerView" type="number" min="0.000001" step="0.000001" value="0.010000" required /> </label>
            <label> Total budget (BMINI) <input id="adBudgetTotal" type="number" min="0.0001" step="0.0001" value="1.0000" required /> </label>
          </div>
          <button class="primary-button full-width" type="submit">Fund and list ad</button>
        </form>
      </article>

      <article class="panel">
        <div class="panel-header"><div><p class="eyebrow muted">Priority</p><h3>Top per-view spenders</h3></div></div>
        ${topSpenders.length ? `
          <div class="transaction-list">
            ${topSpenders.map((item, idx) => `
              <div class="transaction-item">
                <div class="tx-info">
                  <div class="tx-icon">${idx + 1}</div>
                  <div class="tx-meta">
                    <strong>${item.username || item.name || item.walletAddress}</strong>
                    <span>${item.walletAddress || ''}</span>
                  </div>
                </div>
                <div class="tx-value positive">${Number(item.maxBidPerView || 0).toFixed(6)}<br /><span>BMINI/view</span></div>
              </div>
            `).join('')}
          </div>
        ` : '<div class="empty-state">No ad spenders yet.</div>'}
      </article>
    </section>

    <section class="panel">
      <div class="panel-header"><div><p class="eyebrow muted">View ads</p><h3>Choose ad to watch</h3></div></div>
      ${ads.length ? `
        <div class="transaction-list">
          ${ads.map((ad) => `
            <div class="transaction-item">
              <div class="tx-info">
                <div class="tx-icon">${(ad.adType || 'A').slice(0, 1).toUpperCase()}</div>
                <div class="tx-meta">
                  <strong>${ad.title || 'Untitled ad'} · ${ad.sellerUsername || ad.sellerName || ad.sellerWalletAddress}</strong>
                  <span>${ad.adType || 'ad'} · ${Number(ad.bidPerView || 0).toFixed(6)} BMINI/view · Remaining ${Number(ad.budgetRemaining || 0).toFixed(4)}</span>
                </div>
              </div>
              <div class="inline-actions">
                <button class="small-button" type="button" data-open-ad="${ad.id}" ${(!ad.mediaUrl && !ad.targetUrl) ? 'disabled' : ''}>Open</button>
                <button class="primary-button" type="button" data-view-ad="${ad.id}" ${(ad.eligibleToView ? '' : 'disabled')}>${ad.hasViewed ? 'Viewed' : 'Claim view'}</button>
              </div>
            </div>
          `).join('')}
        </div>
      ` : '<div class="empty-state">No ads are active yet.</div>'}
    </section>

    <section class="panel">
      <div class="panel-header"><div><p class="eyebrow muted">Your campaigns</p><h3>Seller summary</h3></div></div>
      ${myAds.length ? `
        <div class="transaction-list">
          ${myAds.map((ad) => `
            <div class="transaction-item">
              <div class="tx-info">
                <div class="tx-icon">${(ad.adType || 'A').slice(0, 1).toUpperCase()}</div>
                <div class="tx-meta">
                  <strong>${ad.title || 'Untitled ad'}</strong>
                  <span>${ad.viewCount || 0} views · ${ad.status || 'active'}</span>
                </div>
              </div>
              <div class="tx-value positive">${Number(ad.budgetRemaining || 0).toFixed(4)}<br /><span>BMINI remaining</span></div>
            </div>
          `).join('')}
        </div>
      ` : '<div class="empty-state">You have not listed any ads yet.</div>'}
    </section>
  `;
}

function renderContacts() {
  return `
    <section class="panel">
      <div class="panel-header"><div><p class="eyebrow muted">Network</p><h3>Saved contacts</h3></div></div>
      <div class="contact-list">${state.contacts.map((contact) => `
        <div class="contact-item">
          <div><strong>${contact.name}</strong><span>${contact.address}</span></div>
          <span class="status-pill neutral">${contact.tag}</span>
        </div>
      `).join('')}</div>
    </section>
  `;
}

function renderReferrals() {
  const referral = state.referralSnapshot;
  if (!referral) {
    return '<section class="panel"><div class="panel-header"><div><p class="eyebrow muted">Referrals</p><h3>Invite and earn</h3></div></div><p>Referral data is not available yet.</p></section>';
  }

  const history = referral.history || [];
  const friends = referral.invitedFriends || [];
  const tiers = Array.isArray(referral.rewardTiers) && referral.rewardTiers.length
    ? referral.rewardTiers
    : [
        { upToMonthlyEvents: 3, multiplier: 1.0 },
        { upToMonthlyEvents: 10, multiplier: 0.85 },
        { upToMonthlyEvents: 25, multiplier: 0.65 },
        { upToMonthlyEvents: null, multiplier: 0.4 }
      ];
  let lowerBound = 1;
  const ladderRows = tiers.map((tier) => {
    const limit = Number.isFinite(Number(tier.upToMonthlyEvents)) ? Number(tier.upToMonthlyEvents) : null;
    const label = limit ? `${lowerBound}-${limit}` : `${lowerBound}+`;
    if (limit) {
      lowerBound = limit + 1;
    }
    return `
      <div class="reward-ladder-row">
        <span>${label}</span>
        <strong>x${Number(tier.multiplier || 0).toFixed(2)}</strong>
      </div>
    `;
  }).join('');

  return `
    <section class="settings-grid">
      <article class="panel">
        <div class="panel-header"><div><p class="eyebrow muted">Your code</p><h3>Share and earn</h3></div></div>
        <div class="address-box">${referral.referralCode || 'Unavailable'}</div>
        <div class="totals"><span>Lifetime earnings</span><strong>${formatBmini(referral.lifetimeEarnings || 0)}</strong></div>
        <div class="totals"><span>Monthly earnings</span><strong>${formatBmini(referral.monthlyEarnings || 0)}</strong></div>
        <div class="totals"><span>Monthly remaining</span><strong>${formatBmini(referral.monthlyRemaining || 0)}</strong></div>
        <div class="totals"><span>Reward events this month</span><strong>${referral.monthlyRewardEvents || 0}</strong></div>
        <div class="totals"><span>Next invite multiplier</span><strong>x${Number(referral.nextRewardMultiplier || 1).toFixed(2)}</strong></div>
        <div class="totals"><span>Invited friends</span><strong>${referral.invitedCount || 0}</strong></div>
        <div class="empty-state">Unlimited invites are supported. Rewards taper with higher monthly referral events to keep growth fair.</div>
        <div class="reward-ladder">
          <div class="reward-ladder-head">
            <span>Monthly events</span>
            <span>Multiplier</span>
          </div>
          ${ladderRows}
        </div>
        ${referral.pendingActivation ? '<div class="empty-state">Referral bonus unlocks after your first transfer.</div>' : ''}
        <button class="primary-button full-width" type="button" id="copyReferralCodePage">Copy referral code</button>
      </article>

      <article class="panel">
        <div class="panel-header"><div><p class="eyebrow muted">Friends</p><h3>Referral network</h3></div></div>
        ${friends.length ? `
          <div class="contact-list">
            ${friends.map((friend) => `
              <div class="contact-item">
                <div><strong>${friend.name}</strong><span>${friend.walletAddress}</span></div>
                <span class="status-pill success">Joined</span>
              </div>
            `).join('')}
          </div>
        ` : '<div class="empty-state">No invited friends yet.</div>'}
      </article>
    </section>

    <section class="panel">
      <div class="panel-header"><div><p class="eyebrow muted">Payouts</p><h3>Referral reward history</h3></div></div>
      ${history.length ? `
        <div class="transaction-list">
          ${history.map((item) => `
            <div class="transaction-item">
              <div class="tx-info">
                <div class="tx-icon">R</div>
                <div class="tx-meta">
                  <strong>${item.value}</strong>
                  <span>Block #${item.blockIndex} · ${item.note || 'Referral bonus'}</span>
                </div>
              </div>
              <div class="tx-value positive">${item.memo || 'Referral'}<br /><span>${item.timestamp || ''}</span></div>
            </div>
          `).join('')}
        </div>
      ` : '<div class="empty-state">No referral payouts yet.</div>'}
    </section>
  `;
}

function renderRankRows(rows = [], metricLabel = 'BMINI') {
  if (!rows.length) {
    return '<div class="empty-state">No ranking data available yet.</div>';
  }

  return rows.map((row, index) => `
    <div class="transaction-item">
      <div class="tx-info">
        <div class="tx-icon">${index + 1}</div>
        <div class="tx-meta">
          <strong>${row.username || row.name || row.walletAddress || 'Unknown'}</strong>
          <span>${row.walletAddress || ''}</span>
        </div>
      </div>
      <div class="tx-value positive">${Number(row.score ?? row.referralEarnings ?? row.maxBidPerView ?? 0).toFixed(4)}<br /><span>${metricLabel}</span></div>
    </div>
  `).join('');
}

function renderLeaderboards() {
  const board = state.leaderboardSnapshot;
  if (!board) {
    return '<section class="panel"><div class="panel-header"><div><p class="eyebrow muted">Leaderboards</p><h3>Top referral earns</h3></div></div><p>Leaderboard data is not available yet.</p></section>';
  }

  const referrals = board.topReferralEarners || {};
  return `
    <section class="settings-grid">
      <article class="panel">
        <div class="panel-header"><div><p class="eyebrow muted">Referrals</p><h3>Daily top earners</h3></div></div>
        <div class="transaction-list">${renderRankRows(referrals.daily || [], 'BMINI/day')}</div>
      </article>
      <article class="panel">
        <div class="panel-header"><div><p class="eyebrow muted">Referrals</p><h3>Weekly top earners</h3></div></div>
        <div class="transaction-list">${renderRankRows(referrals.weekly || [], 'BMINI/week')}</div>
      </article>
    </section>

    <section class="settings-grid">
      <article class="panel">
        <div class="panel-header"><div><p class="eyebrow muted">Referrals</p><h3>Monthly top earners</h3></div></div>
        <div class="transaction-list">${renderRankRows(referrals.monthly || [], 'BMINI/month')}</div>
      </article>
      <article class="panel">
        <div class="panel-header"><div><p class="eyebrow muted">Performance</p><h3>Top contributors</h3></div></div>
        <div class="transaction-list">${renderRankRows(board.topContributors || [], 'contrib')}</div>
      </article>
    </section>

    <section class="settings-grid">
      <article class="panel">
        <div class="panel-header"><div><p class="eyebrow muted">Performance</p><h3>Top earners</h3></div></div>
        <div class="transaction-list">${renderRankRows(board.topEarners || [], 'BMINI')}</div>
      </article>
      <article class="panel">
        <div class="panel-header"><div><p class="eyebrow muted">Performance</p><h3>Top trade</h3></div></div>
        <div class="transaction-list">${renderRankRows(board.topTrade || [], 'volume')}</div>
      </article>
    </section>

    <section class="panel">
      <div class="panel-header"><div><p class="eyebrow muted">Ads</p><h3>Top ad spenders (per view)</h3></div></div>
      <div class="transaction-list">${renderRankRows(board.topAdSpenders || [], 'BMINI/view')}</div>
    </section>
  `;
}

function renderTransactionsPage() {
  const items = (state.recentNetworkTransactions || []).slice(0, 10);
  return `
    <section class="panel">
      <div class="panel-header"><div><p class="eyebrow muted">Network</p><h3>Last 10 transactions</h3></div></div>
      ${items.length ? `
        <div class="transaction-list">
          ${items.map((item) => {
            const positive = item.positive !== false;
            return `
              <div class="transaction-item">
                <div class="tx-info">
                  <div class="tx-icon">${(item.type || 'T').slice(0, 1)}</div>
                  <div class="tx-meta">
                    <strong>${item.type || 'Transaction'} · ${item.username || item.name || item.walletAddress || 'Unknown'}</strong>
                    <span>Block #${item.blockIndex ?? '-'} · ${item.note || ''}</span>
                  </div>
                </div>
                <div class="tx-value ${positive ? 'positive' : 'negative'}">${item.value || '0.0000'}<br /><span>${item.timestamp || ''}</span></div>
              </div>
            `;
          }).join('')}
        </div>
      ` : '<div class="empty-state">No network transactions found yet.</div>'}
    </section>
  `;
}

function renderSettings() {
  return `
    <section class="settings-grid">
      <article class="panel">
        <div class="panel-header"><div><p class="eyebrow muted">Security</p><h3>Wallet controls</h3></div></div>
        <ul class="settings-list">
          <li><span>Passkeys</span><span class="status-pill success">Enabled</span></li>
          <li><span>Auto-lock</span><span>5 minutes</span></li>
          <li><span>Recovery phrase</span><span>Backed up</span></li>
          <li><span>Biometric unlock</span><span class="status-pill neutral">Available</span></li>
        </ul>
      </article>
    </section>
  `;
}

function buildAdminAlerts(admin) {
  const alerts = [];
  const epoch = admin.epoch || {};
  const sqlite = admin.sqlite || {};
  const nodeHealth = admin.networkNode?.health || {};

  const selectedCount = (epoch.selectedValidators || []).length;
  if (selectedCount === 0) {
    alerts.push({
      level: 'critical',
      title: 'Validator Set Empty',
      detail: 'No validators are selected for the current epoch.',
      badge: 'Critical',
      target: 'adminEpochPanel'
    });
  } else {
    alerts.push({
      level: 'ok',
      title: 'Validator Set Active',
      detail: `${selectedCount} validator(s) selected for epoch ${epoch.current || 1}.`,
      badge: 'Healthy',
      target: 'adminEpochPanel'
    });
  }

  const validatedCount = Number(epoch.validatedCount || 0);
  const slashEvents = Number(epoch.slashEvents || 0);
  const slashRatio = validatedCount > 0 ? slashEvents / validatedCount : 0;
  if (slashEvents >= 3 && slashRatio >= 0.3) {
    alerts.push({
      level: 'critical',
      title: 'Slash Spike Detected',
      detail: `${slashEvents} slash events across ${validatedCount} validations.`,
      badge: 'Critical',
      target: 'adminSlashPanel'
    });
  } else if (slashEvents > 0) {
    alerts.push({
      level: 'warn',
      title: 'Slashing Activity',
      detail: `${slashEvents} slash events recorded. Monitor validator behavior.`,
      badge: 'Watch',
      target: 'adminSlashPanel'
    });
  } else {
    alerts.push({
      level: 'ok',
      title: 'No Slashing Spikes',
      detail: 'Validator behavior looks stable so far.',
      badge: 'Healthy',
      target: 'adminSlashPanel'
    });
  }

  if (!sqlite.exists) {
    alerts.push({
      level: 'critical',
      title: 'SQLite Missing',
      detail: 'Persistence file is missing. Runtime state may not survive restart.',
      badge: 'Critical',
      target: 'adminSqlitePanel'
    });
  } else {
    const modifiedMs = sqlite.lastModified ? Date.parse(sqlite.lastModified) : Number.NaN;
    const ageMs = Number.isFinite(modifiedMs) ? Date.now() - modifiedMs : Number.NaN;
    const staleThresholdMs = 15 * 60 * 1000;
    if (Number.isFinite(ageMs) && ageMs > staleThresholdMs) {
      alerts.push({
        level: 'warn',
        title: 'SQLite May Be Stale',
        detail: 'Database file has not changed recently. Confirm writes are healthy.',
        badge: 'Watch',
        target: 'adminSqlitePanel'
      });
    } else {
      alerts.push({
        level: 'ok',
        title: 'SQLite Fresh',
        detail: 'Persistence file is present and recently updated.',
        badge: 'Healthy',
        target: 'adminSqlitePanel'
      });
    }
  }

  if (nodeHealth.ok) {
    const validatorCount = (nodeHealth.validators || []).length;
    alerts.push({
      level: 'ok',
      title: 'Sovereign Node Online',
      detail: `Height ${nodeHealth.height || 0} with ${validatorCount} validator(s). Next proposer ${nodeHealth.nextProposer || 'Unknown'}.`,
      badge: 'Healthy',
      target: 'adminNetworkPanel'
    });
  } else if (nodeHealth.error === 'Node RPC is not configured.') {
    alerts.push({
      level: 'warn',
      title: 'Node RPC Not Configured',
      detail: 'Set BITMINI_NODE_RPC_URL to enable live sovereign node monitoring.',
      badge: 'Setup',
      target: 'adminNetworkPanel'
    });
  } else {
    alerts.push({
      level: 'critical',
      title: 'Node RPC Unreachable',
      detail: nodeHealth.error || 'Unable to reach node health endpoint.',
      badge: 'Critical',
      target: 'adminNetworkPanel'
    });
  }

  return alerts;
}

function renderAdmin() {
  const admin = state.adminSnapshot;
  if (!admin) {
    return '<section class="panel"><div class="panel-header"><div><p class="eyebrow muted">Admin</p><h3>Monitoring</h3></div></div><p>Admin data is not available yet.</p></section>';
  }

  const selected = admin.epoch?.selectedValidators || [];
  const slashHistory = admin.slashHistory || [];
  const sqlite = admin.sqlite || {};
  const metrics = admin.tokenMetrics || {};
  const supply = metrics.supply || {};
  const walletMetrics = metrics.wallets || {};
  const nodeHealth = admin.networkNode?.health || {};
  const nodeMetricPayload = admin.networkNode?.tokenMetrics || {};
  const nodeMetrics = nodeMetricPayload.metrics || {};
  const nodeValidators = nodeHealth.validators || [];
  const nodePeers = nodeHealth.peers || [];
  const adminAlerts = buildAdminAlerts(admin);

  return `
    <section class="admin-alert-strip">
      ${adminAlerts.map((item) => `
        <article class="admin-alert-card ${item.level}" data-admin-target="${item.target}">
          <div class="pill-row">
            <span class="status-pill ${item.level === 'critical' ? 'danger' : item.level === 'warn' ? 'warn' : 'success'}">${item.badge}</span>
          </div>
          <h3>${item.title}</h3>
          <p>${item.detail}</p>
        </article>
      `).join('')}
    </section>

    <section class="settings-grid">
      <article class="panel" id="adminEpochPanel">
        <div class="panel-header"><div><p class="eyebrow muted">Epoch</p><h3>Validator rotation</h3></div></div>
        <ul class="settings-list">
          <li><span>Current epoch</span><span>${admin.epoch?.current || 1}</span></li>
          <li><span>Epoch length</span><span>${admin.epoch?.length || 0} validations</span></li>
          <li><span>Consensus</span><span>${admin.epoch?.consensusLabel || 'Unknown'}</span></li>
          <li><span>Slash events</span><span>${admin.epoch?.slashEvents || 0}</span></li>
        </ul>
        <div class="address-box">Selected validators: ${selected.length ? selected.join(', ') : 'None yet'}</div>
      </article>

      <article class="panel" id="adminSqlitePanel">
        <div class="panel-header"><div><p class="eyebrow muted">SQLite</p><h3>Persistence health</h3></div></div>
        <ul class="settings-list">
          <li><span>Database file</span><span>${sqlite.exists ? 'Present' : 'Missing'}</span></li>
          <li><span>Rows stored</span><span>${sqlite.rowCount || 0}</span></li>
          <li><span>File size</span><span>${sqlite.sizeBytes || 0} bytes</span></li>
          <li><span>Last modified</span><span>${sqlite.lastModified || 'Unknown'}</span></li>
        </ul>
        <div class="address-box">Keys: ${(sqlite.keys || []).join(', ') || 'None'}</div>
      </article>
    </section>

    <section class="settings-grid">
      <article class="panel">
        <div class="panel-header"><div><p class="eyebrow muted">Token Metrics</p><h3>Supply transparency</h3></div></div>
        <ul class="settings-list">
          <li><span>Minted</span><span>${formatBmini(supply.minted || 0)}</span></li>
          <li><span>Max supply</span><span>${formatBmini(supply.max || 0)}</span></li>
          <li><span>Remaining</span><span>${formatBmini(supply.remaining || 0)}</span></li>
          <li><span>Locked reserve</span><span>${formatBmini(supply.lockedGenesisReserve || 0)}</span></li>
        </ul>
      </article>

      <article class="panel">
        <div class="panel-header"><div><p class="eyebrow muted">Wallet Activity</p><h3>Network participation</h3></div></div>
        <ul class="settings-list">
          <li><span>Total wallets</span><span>${walletMetrics.total || 0}</span></li>
          <li><span>Active 24h</span><span>${walletMetrics.active24h || 0}</span></li>
          <li><span>Active 7d</span><span>${walletMetrics.active7d || 0}</span></li>
        </ul>
      </article>
    </section>

    <section class="settings-grid">
      <article class="panel" id="adminNetworkPanel">
        <div class="panel-header"><div><p class="eyebrow muted">Sovereign Node</p><h3>Live operations</h3></div></div>
        <ul class="settings-list">
          <li><span>Status</span><span>${nodeHealth.ok ? 'Online' : 'Offline'}</span></li>
          <li><span>Chain ID</span><span>${nodeHealth.chainId || 'Unknown'}</span></li>
          <li><span>Block height</span><span>${nodeHealth.height ?? 0}</span></li>
          <li><span>Next proposer</span><span>${nodeHealth.nextProposer || 'Unknown'}</span></li>
          <li><span>Peers</span><span>${nodePeers.length}</span></li>
        </ul>
        <div class="address-box">Validators: ${nodeValidators.length ? nodeValidators.join(', ') : 'None reported'}</div>
        ${nodeHealth.error ? `<div class="empty-state">${nodeHealth.error}</div>` : ''}
      </article>

      <article class="panel">
        <div class="panel-header"><div><p class="eyebrow muted">Node Supply</p><h3>On-chain metrics</h3></div></div>
        <ul class="settings-list">
          <li><span>Circulating</span><span>${formatBmini(nodeMetrics.circulating || 0)}</span></li>
          <li><span>Locked</span><span>${formatBmini(nodeMetrics.locked || 0)}</span></li>
          <li><span>Minted</span><span>${formatBmini(nodeMetrics.minted || 0)}</span></li>
          <li><span>Max</span><span>${formatBmini(nodeMetrics.max || 0)}</span></li>
        </ul>
      </article>
    </section>

    <section class="panel" id="adminSlashPanel">
      <div class="panel-header"><div><p class="eyebrow muted">Slashing</p><h3>Recent slash history</h3></div></div>
      ${slashHistory.length ? `
        <div class="transaction-list">
          ${slashHistory.map((item) => `
            <div class="transaction-item">
              <div class="tx-info">
                <div class="tx-icon">!</div>
                <div class="tx-meta">
                  <strong>${item.value}</strong>
                  <span>Block #${item.blockIndex} · ${item.note || 'Penalty'}</span>
                </div>
              </div>
              <div class="tx-value negative">${item.recipient}<br /><span>${item.timestamp || ''}</span></div>
            </div>
          `).join('')}
        </div>
      ` : '<div class="empty-state">No slash events recorded.</div>'}
    </section>
  `;
}

function setCurrentView(view) {
  if (!view || view === state.currentView) {
    return;
  }

  state.lastView = state.currentView;
  state.currentView = view;
  renderView();
}

function renderAuthGate() {
  return `
    <section class="panel send-screen">
      <div class="panel-header">
        <div><p class="eyebrow muted">Wallet access</p><h3>Authentication required</h3></div>
      </div>
      <div class="empty-state" style="margin-bottom: 12px;">
        Your Bitmini wallet session is missing or expired. Please log in from the home page before opening the wallet dashboard.
      </div>
      <div class="inline-actions">
        <a class="primary-button" href="/">Go to home</a>
      </div>
    </section>
  `;
}

function renderView() {
  const appView = document.getElementById('appView');
  const pageTitle = document.getElementById('pageTitle');
  if (!appView || !pageTitle) return;

  const isAuthenticated = Boolean(auth.sessionToken && auth.walletAddress);
  if (!isAuthenticated && state.currentView !== 'register') {
    pageTitle.textContent = 'Wallet access';
    appView.innerHTML = renderAuthGate();
    return;
  }

  pageTitle.textContent = navLabels[state.currentView];

  const viewMap = {
    home: renderHome,
    wallet: renderWallet,
    register: renderRegister,
    mine: renderMine,
    send: renderSend,
    receive: renderReceive,
    'buy-sell': renderBuySell,
    activity: renderActivity,
    markets: renderMarkets,
    ads: renderAds,
    contacts: renderContacts,
    referrals: renderReferrals,
    leaderboards: renderLeaderboards,
    transactions: renderTransactionsPage,
    admin: renderAdmin,
    settings: renderSettings
  };

  appView.innerHTML = viewMap[state.currentView]?.() || renderHome();
  const qrDisplay = document.getElementById('qrCode');
  if (qrDisplay) {
    const walletQrPayload = `bitmini:${state.walletAddress}`;
    renderRealQrCode(qrDisplay, walletQrPayload);
  }
  const receiveQr = document.getElementById('receiveQr');
  if (receiveQr) {
    const receiveQrPayload = `bitmini:${state.walletAddress}`;
    renderRealQrCode(receiveQr, receiveQrPayload);
  }
  bindDynamicEvents();
}

async function handleTransferSubmit(event, formType = 'main') {
  event.preventDefault();
  const amountInput = formType === 'main' ? document.getElementById('amount') : document.getElementById('pageAmount');
  const recipientInput = formType === 'main' ? document.getElementById('recipient') : document.getElementById('pageRecipient');
  const noteInput = formType === 'main' ? document.getElementById('note') : document.getElementById('pageMemo');

  const amount = Number(amountInput?.value || 0);
  const recipient = recipientInput?.value.trim() || '';
  const memo = noteInput?.value.trim() || 'Transfer';

  if (!recipient || amount <= 0) {
    alert('Please enter a valid recipient and amount.');
    return;
  }

  try {
    const response = await fetch('/api/send', {
      method: 'POST',
      headers: authedHeaders(),
      body: JSON.stringify({ walletAddress: auth.walletAddress || state.walletAddress, amount, recipient, memo })
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || 'Unable to send BMINI');
    }
    await loadWalletData();
    state.currentView = 'activity';
    renderView();
    alert(result.message || 'Transfer queued successfully.');
  } catch (error) {
    alert(error.message || 'Unable to send BMINI');
  }
}

function bindDynamicEvents() {
  document.querySelectorAll('.nav-item').forEach((button) => {
    button.classList.toggle('active', button.dataset.view === state.currentView);
    button.onclick = () => setCurrentView(button.dataset.view);
  });

  document.querySelectorAll('[data-view]').forEach((element) => {
    if (element.dataset.view && element.dataset.view !== state.currentView) {
      element.onclick = () => setCurrentView(element.dataset.view);
    }
  });

  document.getElementById('backButton')?.addEventListener('click', () => {
    const previousView = state.lastView && state.lastView !== state.currentView ? state.lastView : 'home';
    state.lastView = state.currentView;
    state.currentView = previousView;
    renderView();
  });

  document.getElementById('homeButton')?.addEventListener('click', () => {
    state.lastView = state.currentView;
    state.currentView = 'home';
    renderView();
  });

  document.getElementById('headerSend')?.addEventListener('click', () => {
    setCurrentView('send');
  });

  document.getElementById('addWallet')?.addEventListener('click', () => {
    setCurrentView('wallet');
  });

  const amountInput = document.getElementById('amount');
  const totalElement = document.getElementById('totalAmount');
  if (amountInput && totalElement) {
    const updateTotal = () => {
      const amount = Number(amountInput.value) || 0;
      totalElement.textContent = formatUsd(amount * state.price);
    };
    amountInput.addEventListener('input', updateTotal);
    updateTotal();
  }

  const pageAmount = document.getElementById('pageAmount');
  const pageTotal = document.getElementById('pageTotal');
  if (pageAmount && pageTotal) {
    const updatePageTotal = () => {
      const amount = Number(pageAmount.value) || 0;
      pageTotal.textContent = formatUsd(amount * state.price);
    };
    pageAmount.addEventListener('input', updatePageTotal);
    updatePageTotal();
  }

  document.getElementById('sendForm')?.addEventListener('submit', (event) => handleTransferSubmit(event, 'main'));
  document.getElementById('sendFormPage')?.addEventListener('submit', (event) => handleTransferSubmit(event, 'page'));

  document.getElementById('registerForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const name = document.getElementById('registerName')?.value.trim();
    const username = document.getElementById('registerUsername')?.value.trim();
    const dateOfBirth = document.getElementById('registerDob')?.value || '';
    const zipCode = document.getElementById('registerZip')?.value.trim();
    const email = document.getElementById('registerEmail')?.value.trim();
    const password = document.getElementById('registerPassword')?.value || '';
    const referralCode = document.getElementById('registerReferralCode')?.value.trim();

    try {
      const response = await fetch('/api/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, username, dateOfBirth, zipCode, email, password, referralCode })
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || 'Unable to register wallet');
      }

      if (result.sessionToken && result.wallet?.walletAddress) {
        auth.sessionToken = result.sessionToken;
        auth.walletAddress = result.wallet.walletAddress;
        localStorage.setItem('bitminiSessionToken', auth.sessionToken);
        localStorage.setItem('bitminiWalletAddress', auth.walletAddress);
      }

      await loadWalletData();
      state.currentView = 'home';
      renderView();

      const link = document.createElement('a');
      link.href = result.downloadUrl;
      link.download = 'bitmini-wallet.json';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      if (result.referralBonus > 0) {
        alert(`${result.message || 'Wallet created successfully.'} Referral bonus: ${result.referralBonus} BMINI`);
      } else {
        alert(result.message || 'Wallet created successfully.');
      }
    } catch (error) {
      alert(error.message || 'Unable to register wallet.');
    }
  });

  document.getElementById('buyForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    alert('Real money integrations are not enabled in this deployment. Fiat rails must be configured before this wallet can buy or sell BMINI.');
  });

  document.getElementById('consensusModeSelect')?.addEventListener('change', async (event) => {
    const mode = event.target.value;
    const walletAddress = auth.walletAddress || document.getElementById('mineWalletAddress')?.value || state.walletAddress;

    try {
      const response = await fetch('/api/consensus', {
        method: 'POST',
        headers: authedHeaders(),
        body: JSON.stringify({ walletAddress, mode })
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || 'Consensus update failed');
      }
      await loadWalletData();
      state.currentView = 'mine';
      renderView();
      alert(result.message || 'Consensus mode updated.');
    } catch (error) {
      alert(error.message || 'Consensus update failed.');
    }
  });

  document.getElementById('stakeButton')?.addEventListener('click', async () => {
    const amount = Number(document.getElementById('stakeAmount')?.value || 0);
    const walletAddress = auth.walletAddress || document.getElementById('mineWalletAddress')?.value || state.walletAddress;

    try {
      const response = await fetch('/api/stake', {
        method: 'POST',
        headers: authedHeaders(),
        body: JSON.stringify({ walletAddress, amount })
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || 'Stake lock failed');
      }
      await loadWalletData();
      state.currentView = 'mine';
      renderView();
      alert(result.message || 'Stake locked successfully.');
    } catch (error) {
      alert(error.message || 'Stake lock failed.');
    }
  });

  document.getElementById('slashButton')?.addEventListener('click', async () => {
    const reason = document.getElementById('slashReason')?.value.trim() || 'Validator misbehavior';
    const walletAddress = auth.walletAddress || document.getElementById('mineWalletAddress')?.value || state.walletAddress;

    try {
      const response = await fetch('/api/slash', {
        method: 'POST',
        headers: authedHeaders(),
        body: JSON.stringify({ walletAddress, reason })
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || 'Slashing failed');
      }
      await loadWalletData();
      state.currentView = 'mine';
      renderView();
      alert(`${result.penalty} BMINI slashed for validator penalty.`);
    } catch (error) {
      alert(error.message || 'Slashing failed.');
    }
  });

  document.getElementById('consensusForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const reward = Number(document.getElementById('mineReward')?.value || 2);
    const walletAddress = auth.walletAddress || document.getElementById('mineWalletAddress')?.value || state.walletAddress;

    try {
      const response = await fetch('/api/validate', {
        method: 'POST',
        headers: authedHeaders(),
        body: JSON.stringify({ walletAddress, reward })
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || 'Validation failed');
      }
      await loadWalletData();
      state.currentView = 'home';
      renderView();
      alert(`${result.reward} BMINI validated successfully (${result.consensus?.label || 'consensus'}).`);
    } catch (error) {
      alert(error.message || 'Validation failed.');
    }
  });

  document.getElementById('copyAddress')?.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(state.walletAddress);
      const button = document.getElementById('copyAddress');
      if (button) {
        button.textContent = 'Copied';
        setTimeout(() => { button.textContent = 'Copy'; }, 1000);
      }
    } catch (error) {
      console.error('Clipboard error:', error);
    }
  });

  document.getElementById('copyReceiveAddress')?.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(state.walletAddress);
      const button = document.getElementById('copyReceiveAddress');
      if (button) {
        button.textContent = 'Copied';
        setTimeout(() => { button.textContent = 'Copy'; }, 1000);
      }
    } catch (error) {
      console.error('Clipboard error:', error);
    }
  });

  document.getElementById('copyReferralCode')?.addEventListener('click', async () => {
    try {
      if (!state.referralCode) return;
      await navigator.clipboard.writeText(state.referralCode);
      const button = document.getElementById('copyReferralCode');
      if (button) {
        button.textContent = 'Copied';
        setTimeout(() => { button.textContent = 'Copy referral code'; }, 1000);
      }
    } catch (error) {
      console.error('Clipboard error:', error);
    }
  });

  document.getElementById('copyReferralCodePage')?.addEventListener('click', async () => {
    try {
      const code = state.referralSnapshot?.referralCode || state.referralCode;
      if (!code) return;
      await navigator.clipboard.writeText(code);
      const button = document.getElementById('copyReferralCodePage');
      if (button) {
        button.textContent = 'Copied';
        setTimeout(() => { button.textContent = 'Copy referral code'; }, 1000);
      }
    } catch (error) {
      console.error('Clipboard error:', error);
    }
  });

  document.querySelectorAll('.admin-alert-card[data-admin-target]').forEach((card) => {
    card.addEventListener('click', () => {
      const targetId = card.getAttribute('data-admin-target');
      const target = targetId ? document.getElementById(targetId) : null;
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  document.getElementById('createAdForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const adType = document.getElementById('adType')?.value;
    const title = document.getElementById('adTitle')?.value.trim();
    const description = document.getElementById('adDescription')?.value.trim();
    const mediaUrl = document.getElementById('adMediaUrl')?.value.trim();
    const targetUrl = document.getElementById('adTargetUrl')?.value.trim();
    const bidPerView = Number(document.getElementById('adBidPerView')?.value || 0);
    const budgetTotal = Number(document.getElementById('adBudgetTotal')?.value || 0);

    try {
      const response = await fetch('/api/ads/create', {
        method: 'POST',
        headers: authedHeaders(),
        body: JSON.stringify({ walletAddress: auth.walletAddress || state.walletAddress, adType, title, description, mediaUrl, targetUrl, bidPerView, budgetTotal })
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || 'Unable to create ad');
      }
      await loadWalletData();
      state.currentView = 'ads';
      renderView();
      alert(result.message || 'Ad campaign created.');
    } catch (error) {
      alert(error.message || 'Unable to create ad');
    }
  });

  document.getElementById('setCategoryForm')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const userCategory = document.getElementById('walletCategory')?.value;
    try {
      const response = await fetch('/api/wallet/category', {
        method: 'POST',
        headers: authedHeaders(),
        body: JSON.stringify({ walletAddress: auth.walletAddress || state.walletAddress, userCategory })
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || 'Unable to update wallet category');
      }
      await loadWalletData();
      state.currentView = 'ads';
      renderView();
      alert(result.message || 'Wallet category updated.');
    } catch (error) {
      alert(error.message || 'Unable to update wallet category');
    }
  });

  document.querySelectorAll('[data-open-ad]').forEach((button) => {
    button.addEventListener('click', () => {
      const adId = button.getAttribute('data-open-ad');
      const ad = (state.adsSnapshot?.ads || []).find((entry) => entry.id === adId);
      const link = ad?.mediaUrl || ad?.targetUrl;
      if (link) {
        window.open(link, '_blank', 'noopener,noreferrer');
      }
    });
  });

  document.querySelectorAll('[data-view-ad]').forEach((button) => {
    button.addEventListener('click', async () => {
      const adId = button.getAttribute('data-view-ad');
      if (!adId) return;
      try {
        const response = await fetch('/api/ads/view', {
          method: 'POST',
          headers: authedHeaders(),
          body: JSON.stringify({ walletAddress: auth.walletAddress || state.walletAddress, adId })
        });
        const result = await response.json();
        if (!response.ok) {
          throw new Error(result.error || 'Unable to claim ad view');
        }
        await loadWalletData();
        state.currentView = 'ads';
        renderView();
        alert(`${result.message || 'Ad view recorded.'} Reward: ${Number(result.reward || 0).toFixed(6)} BMINI`);
      } catch (error) {
        alert(error.message || 'Unable to claim ad view');
      }
    });
  });
}

loadWalletData();
