function persistSession(sessionToken, walletAddress) {
  localStorage.setItem("bitminiSessionToken", sessionToken);
  localStorage.setItem("bitminiWalletAddress", walletAddress);
}

async function fetchPhaseAStatus() {
  const container = document.getElementById("phaseAStatus");
  if (!container) return;

  try {
    const response = await fetch("/api/network/bootstrap");
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "Phase A status unavailable");
    }

    const seedNodes = (payload.seedNodes || []).map((node) => `<li>${node}</li>`).join("") || "<li>Seed nodes pending launch</li>";
    const bootstrapPeers = (payload.bootstrapPeers || []).map((peer) => `<li>${peer}</li>`).join("") || "<li>Bootstrap peers pending launch</li>";

    container.innerHTML = `
      <div class="phase-badge">Phase ${payload.phase} · ${payload.status}</div>
      <div class="phase-meta">
        <strong>${payload.network}</strong>
        <span>Chain ID: ${payload.chainId}</span>
      </div>
      <div class="phase-lists">
        <div>
          <h3>Seed nodes</h3>
          <ul>${seedNodes}</ul>
        </div>
        <div>
          <h3>Bootstrap peers</h3>
          <ul>${bootstrapPeers}</ul>
        </div>
      </div>
    `;
  } catch (error) {
    container.innerHTML = `<div class="phase-badge error">Launch metadata unavailable</div><p>${error.message}</p>`;
  }
}

async function fetchSecurityLayers() {
  const container = document.getElementById("securityLayers");
  if (!container) return;

  try {
    const response = await fetch("/api/security-layer");
    const payload = await response.json();
    if (!response.ok || !payload.layers) {
      throw new Error(payload.error || "Security layer fetch failed");
    }

    container.innerHTML = payload.layers
      .map(
        (item) => `
        <article class="mini-card">
          <h3>${item.name}</h3>
          <p>${item.details}</p>
        </article>
      `
      )
      .join("");
  } catch (error) {
    container.innerHTML = `<article class="mini-card"><h3>Security details unavailable</h3><p>${error.message}</p></article>`;
  }
}

function asDisplayIdentity(item) {
  return item?.username || item?.name || item?.walletAddress || "Unknown wallet";
}

function asCompactAddress(value) {
  const address = String(value || "").trim();
  if (address.length <= 14) return address;
  return `${address.slice(0, 7)}...${address.slice(-5)}`;
}

function renderTopEarners(items) {
  const container = document.getElementById("homepageTopEarners");
  if (!container) return;

  if (!Array.isArray(items) || !items.length) {
    container.innerHTML = `<article class="mini-card"><h3>No earning data yet</h3><p>Top earners will appear here after network activity is recorded.</p></article>`;
    return;
  }

  container.innerHTML = items
    .slice(0, 5)
    .map(
      (item, idx) => `
        <article class="mini-card rank-item">
          <h3>#${idx + 1} ${asDisplayIdentity(item)}</h3>
          <p>${asCompactAddress(item.walletAddress)}</p>
          <strong>${Number(item.metric || item.referralEarnings || item.score || 0).toFixed(4)} BMINI</strong>
        </article>
      `
    )
    .join("");
}

function renderRecentTransactions(items) {
  const container = document.getElementById("homepageTransactions");
  if (!container) return;

  if (!Array.isArray(items) || !items.length) {
    container.innerHTML = `<article class="mini-card"><h3>No transactions yet</h3><p>Recent ledger transactions will appear here as activity starts.</p></article>`;
    return;
  }

  container.innerHTML = items
    .slice(0, 5)
    .map(
      (item) => `
        <article class="mini-card tx-item">
          <h3>${item.type || "Transaction"}</h3>
          <p>${asDisplayIdentity(item)} · ${asCompactAddress(item.walletAddress)}</p>
          <strong>${Number(item.value ?? item.amount ?? 0).toFixed(4)} BMINI</strong>
        </article>
      `
    )
    .join("");
}

async function fetchHomepageActivity() {
  try {
    const [leadersResp, txResp] = await Promise.all([
      fetch("/api/leaderboards?limit=10"),
      fetch("/api/transactions/recent?limit=10")
    ]);
    const [leadersPayload, txPayload] = await Promise.all([leadersResp.json(), txResp.json()]);

    if (!leadersResp.ok || !leadersPayload.ok) {
      throw new Error(leadersPayload.error || "Unable to load top earners");
    }
    if (!txResp.ok || !txPayload.ok) {
      throw new Error(txPayload.error || "Unable to load recent transactions");
    }

    renderTopEarners(leadersPayload.topEarners || []);
    renderRecentTransactions(txPayload.transactions || []);
  } catch (error) {
    const earners = document.getElementById("homepageTopEarners");
    const tx = document.getElementById("homepageTransactions");
    if (earners) {
      earners.innerHTML = `<article class="mini-card"><h3>Top earners unavailable</h3><p>${error.message}</p></article>`;
    }
    if (tx) {
      tx.innerHTML = `<article class="mini-card"><h3>Transactions unavailable</h3><p>${error.message}</p></article>`;
    }
  }
}

function bindRegisterForm() {
  const form = document.getElementById("registerForm");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = document.getElementById("registerName")?.value.trim() || "New User";
    const username = document.getElementById("registerUsername")?.value.trim() || "";
    const dateOfBirth = document.getElementById("registerDob")?.value || "";
    const zipCode = document.getElementById("registerZip")?.value.trim() || "";
    const email = document.getElementById("registerEmail")?.value.trim() || "";
    const password = document.getElementById("registerPassword")?.value || "";
    const referralCode = document.getElementById("registerReferralCode")?.value.trim() || "";

    try {
      const response = await fetch("/api/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, username, dateOfBirth, zipCode, email, password, referralCode }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Unable to create wallet");
      }

      persistSession(payload.sessionToken, payload.wallet.walletAddress);
      window.location.href = `/app?wallet=${encodeURIComponent(payload.wallet.walletAddress)}&session=${encodeURIComponent(payload.sessionToken)}`;
    } catch (error) {
      alert(error.message || "Unable to create wallet");
    }
  });
}

function bindLoginForm() {
  const form = document.getElementById("loginForm");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const walletAddress = document.getElementById("loginWalletAddress")?.value.trim() || "";
    const username = document.getElementById("loginUsername")?.value.trim() || "";
    const method = document.getElementById("loginMethod")?.value || "password";
    const secret = document.getElementById("loginSecret")?.value || "";

    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ walletAddress, username, method, secret }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Wallet access denied");
      }

      persistSession(payload.sessionToken, payload.wallet.walletAddress);
      window.location.href = `/app?wallet=${encodeURIComponent(payload.wallet.walletAddress)}&session=${encodeURIComponent(payload.sessionToken)}`;
    } catch (error) {
      alert(error.message || "Wallet access denied");
    }
  });
}

fetchPhaseAStatus();
fetchSecurityLayers();
fetchHomepageActivity();
bindRegisterForm();
bindLoginForm();
