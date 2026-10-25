const state = {
  currentView: 'home',
  balance: 0,
  price: 0,
  walletAddress: 'B8N9xZQ7v4h3mt2v8k1c6f0p9d3q7r4w',
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

const navLabels = {
  home: 'Bitmini Wallet',
  wallet: 'Wallet Overview',
  send: 'Send Bitmini',
  receive: 'Receive Bitmini',
  'buy-sell': 'Buy / Sell',
  activity: 'Transaction Activity',
  markets: 'Market Explorer',
  contacts: 'Contacts',
  settings: 'Security & Settings'
};

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

function createQrPattern() {
  const primaryQr = document.getElementById('qrCode');
  if (primaryQr) {
    primaryQr.innerHTML = createQrMarkup();
  }

  const receiveQr = document.getElementById('receiveQr');
  if (receiveQr) {
    receiveQr.innerHTML = createQrMarkup();
  }
}

function renderTransactions(items = state.transactions) {
  if (!items.length) {
    return '<div class="empty-state">No transactions yet. Your genesis block is waiting.</div>';
  }

  return items
    .map((item) => {
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
    })
    .join('');
}

function renderAlerts() {
  return state.alerts
    .map(
      (item) => `
        <li class="alert-item">
          <div>
            <strong>${item.label}</strong>
            <span>${item.status}</span>
          </div>
          <span class="delta positive">${item.value}</span>
        </li>
      `
    )
    .join('');
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
          <h3 id="walletBalance">${formatBmini(state.balance)}</h3>
          <p class="fiat-value">≈ ${formatUsd(state.balance * state.price)} USD</p>
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
            <strong>${formatUsd(state.balance * state.price)}</strong>
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
          <label>
            Recipient address
            <input id="recipient" type="text" value="B8N9xZ...a32f7" />
          </label>
          <div class="split-row">
            <label>
              Amount
              <input id="amount" type="number" step="0.0001" min="0" value="0" />
            </label>
            <label>
              Fee
              <input type="text" value="0.0000" readonly />
            </label>
          </div>
          <label>
            Optional note
            <input id="note" type="text" value="Client payment" />
          </label>
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
          <span id="walletAddress">${state.walletAddress}</span>
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

      <article class="panel kyc-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow muted">Compliance</p>
            <h3>KYC status</h3>
          </div>
          <span class="status-pill success">Approved</span>
        </div>
        <div class="kyc-detail">
          <div>
            <label>Tier</label>
            <strong>Verified</strong>
          </div>
          <div>
            <label>Daily limit</label>
            <strong>$250,000</strong>
          </div>
        </div>
        <ul class="check-list">
          <li>Identity verified</li>
          <li>AML screening passed</li>
          <li>Sanctions check cleared</li>
        </ul>
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
          <span class="status-pill success">Genesis wallet</span>
        </div>
        <div class="wallet-summary-grid">
          <div>
            <label>Balance</label>
            <strong>${formatBmini(state.balance)}</strong>
          </div>
          <div>
            <label>Fiat value</label>
            <strong>${formatUsd(state.balance * state.price)}</strong>
          </div>
          <div>
            <label>Mode</label>
            <strong>Hybrid staged</strong>
          </div>
        </div>
      </article>

      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow muted">Wallet address</p>
            <h3>Receive address</h3>
          </div>
        </div>
        <div class="address-box">${state.walletAddress}</div>
      </article>
    </section>
  `;
}

function renderSend() {
  return `
    <section class="panel send-screen">
      <div class="panel-header">
        <div>
          <p class="eyebrow muted">Transfer</p>
          <h3>Send BMINI</h3>
        </div>
      </div>
      <form id="sendFormPage" class="send-form large">
        <label>
          Recipient address
          <input id="pageRecipient" type="text" value="" placeholder="Enter wallet address" />
        </label>
        <div class="split-row">
          <label>
            Amount
            <input id="pageAmount" type="number" min="0" step="0.0001" value="0" />
          </label>
          <label>
            Fee
            <input type="text" value="0.0000" readonly />
          </label>
        </div>
        <label>
          Memo
          <input id="pageMemo" type="text" placeholder="Optional message" />
        </label>
        <div class="totals">
          <span>Total</span>
          <strong id="pageTotal">$0.00</strong>
        </div>
        <button class="primary-button full-width" type="submit">Send now</button>
      </form>
    </section>
  `;
}

function renderReceive() {
  return `
    <section class="panel receive-screen">
      <div class="panel-header">
        <div>
          <p class="eyebrow muted">Receive</p>
          <h3>Payment request</h3>
        </div>
      </div>
      <div class="receive-layout">
        <div class="qr-card large">
          <div id="receiveQr" class="qr-code large-qr" aria-label="Bitmini payment QR code"></div>
        </div>
        <div class="receive-info">
          <div class="address-box">${state.walletAddress}</div>
          <div class="inline-actions">
            <button class="small-button" id="copyReceiveAddress">Copy</button>
            <button class="ghost-button" id="shareRequest">Share</button>
          </div>
          <label>
            Request amount
            <input type="number" min="0" step="0.0001" value="0" />
          </label>
        </div>
      </div>
    </section>
  `;
}

function renderBuySell() {
  return `
    <section class="panel">
      <div class="panel-header">
        <div>
          <p class="eyebrow muted">On-ramp</p>
          <h3>Buy / Sell</h3>
        </div>
      </div>
      <div class="market-grid">
        <div class="market-card">
          <label>Buy BMINI</label>
          <strong>$250.00</strong>
          <span>1.1 BMINI</span>
          <button class="primary-button full-width">Buy now</button>
        </div>
        <div class="market-card">
          <label>Sell BMINI</label>
          <strong>$250.00</strong>
          <span>1.1 BMINI</span>
          <button class="ghost-button full-width">Sell now</button>
        </div>
      </div>
    </section>
  `;
}

function renderActivity() {
  return `
    <section class="panel">
      <div class="panel-header">
        <div>
          <p class="eyebrow muted">History</p>
          <h3>All activity</h3>
        </div>
      </div>
      <div class="transaction-list">${renderTransactions()}</div>
    </section>
  `;
}

function renderMarkets() {
  return `
    <section class="market-grid">
      <article class="panel market-card-wide">
        <div class="panel-header">
          <div>
            <p class="eyebrow muted">Market</p>
            <h3>Bitmini price board</h3>
          </div>
        </div>
        <div class="price-row big">
          <strong>${formatUsd(state.price)}</strong>
          <span class="delta positive">+8.32%</span>
        </div>
        <div class="sparkline large" aria-hidden="true">
          <span style="height: 20%"></span>
          <span style="height: 34%"></span>
          <span style="height: 30%"></span>
          <span style="height: 46%"></span>
          <span style="height: 51%"></span>
          <span style="height: 64%"></span>
          <span style="height: 72%"></span>
          <span style="height: 69%"></span>
          <span style="height: 80%"></span>
          <span style="height: 76%"></span>
          <span style="height: 90%"></span>
          <span style="height: 100%"></span>
        </div>
      </article>
      <article class="panel market-card-wide">
        <div class="panel-header">
          <div>
            <p class="eyebrow muted">Monitoring</p>
            <h3>Alerts</h3>
          </div>
        </div>
        <ul class="alert-list">${renderAlerts()}</ul>
      </article>
    </section>
  `;
}

function renderContacts() {
  return `
    <section class="panel">
      <div class="panel-header">
        <div>
          <p class="eyebrow muted">Network</p>
          <h3>Saved contacts</h3>
        </div>
      </div>
      <div class="contact-list">
        ${state.contacts
          .map(
            (contact) => `
              <div class="contact-item">
                <div>
                  <strong>${contact.name}</strong>
                  <span>${contact.address}</span>
                </div>
                <span class="status-pill neutral">${contact.tag}</span>
              </div>
            `
          )
          .join('')}
      </div>
    </section>
  `;
}

function renderSettings() {
  return `
    <section class="settings-grid">
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow muted">Security</p>
            <h3>Wallet controls</h3>
          </div>
        </div>
        <ul class="settings-list">
          <li><span>Passkeys</span><span class="status-pill success">Enabled</span></li>
          <li><span>Auto-lock</span><span>5 minutes</span></li>
          <li><span>Recovery phrase</span><span>Backed up</span></li>
          <li><span>Biometric unlock</span><span class="status-pill neutral">Available</span></li>
        </ul>
      </article>
      <article class="panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow muted">Compliance</p>
            <h3>Account status</h3>
          </div>
        </div>
        <ul class="settings-list">
          <li><span>KYC</span><span class="status-pill success">Approved</span></li>
          <li><span>AML</span><span class="status-pill success">Passed</span></li>
          <li><span>Limits</span><span>$250,000/day</span></li>
          <li><span>Region</span><span>US / EU</span></li>
        </ul>
      </article>
    </section>
  `;
}

function renderView() {
  const appView = document.getElementById('appView');
  const pageTitle = document.getElementById('pageTitle');
  pageTitle.textContent = navLabels[state.currentView];

  if (state.currentView === 'home') {
    appView.innerHTML = renderHome();
  } else if (state.currentView === 'wallet') {
    appView.innerHTML = renderWallet();
  } else if (state.currentView === 'send') {
    appView.innerHTML = renderSend();
  } else if (state.currentView === 'receive') {
    appView.innerHTML = renderReceive();
  } else if (state.currentView === 'buy-sell') {
    appView.innerHTML = renderBuySell();
  } else if (state.currentView === 'activity') {
    appView.innerHTML = renderActivity();
  } else if (state.currentView === 'markets') {
    appView.innerHTML = renderMarkets();
  } else if (state.currentView === 'contacts') {
    appView.innerHTML = renderContacts();
  } else {
    appView.innerHTML = renderSettings();
  }

  createQrPattern();
  bindDynamicEvents();
}

function bindDynamicEvents() {
  document.querySelectorAll('.nav-item').forEach((button) => {
    button.classList.toggle('active', button.dataset.view === state.currentView);
    button.onclick = () => {
      state.currentView = button.dataset.view;
      renderView();
    };
  });

  document.querySelectorAll('[data-view]').forEach((element) => {
    if (element.dataset.view) {
      element.onclick = () => {
        state.currentView = element.dataset.view;
        renderView();
      };
    }
  });

  document.getElementById('headerSend')?.addEventListener('click', () => {
    state.currentView = 'send';
    renderView();
  });

  document.getElementById('addWallet')?.addEventListener('click', () => {
    state.currentView = 'wallet';
    renderView();
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

  document.getElementById('sendForm')?.addEventListener('submit', (event) => {
    event.preventDefault();
    const amount = Number(document.getElementById('amount').value || 0);
    const recipient = document.getElementById('recipient').value.trim();
    if (!recipient || amount <= 0) {
      alert('Please enter a valid recipient and amount.');
      return;
    }
    alert(`Reviewing transfer of ${amount} BMINI to ${recipient}`);
  });

  document.getElementById('sendFormPage')?.addEventListener('submit', (event) => {
    event.preventDefault();
    const amount = Number(document.getElementById('pageAmount').value || 0);
    const recipient = document.getElementById('pageRecipient').value.trim();
    if (!recipient || amount <= 0) {
      alert('Please enter a valid recipient and amount.');
      return;
    }
    alert(`Transfer of ${amount} BMINI to ${recipient} queued.`);
  });

  document.getElementById('copyAddress')?.addEventListener('click', async () => {
    await navigator.clipboard.writeText(state.walletAddress);
    const button = document.getElementById('copyAddress');
    button.textContent = 'Copied';
    setTimeout(() => {
      button.textContent = 'Copy';
    }, 1000);
  });

  document.getElementById('copyReceiveAddress')?.addEventListener('click', async () => {
    await navigator.clipboard.writeText(state.walletAddress);
    const button = document.getElementById('copyReceiveAddress');
    button.textContent = 'Copied';
    setTimeout(() => {
      button.textContent = 'Copy';
    }, 1000);
  });
}

renderView();
