const socket = io({
  transports: ["websocket", "polling"],
  timeout: 20000,
  forceNew: true,
});

let username = null;
let currentOpponent = null;
let isConnected = false;
let searchTimeout = null;

// 🔐 Login/Registratie
async function register() {
  username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value.trim();
  if (!username || !password)
    return showMessage("auth-message", "Vul gebruikersnaam en wachtwoord in");

  const res = await fetch("/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  const data = await res.json();
  if (res.ok) {
    startGame(data.floor);
  } else {
    showMessage("auth-message", data.error || "Registratie mislukt");
  }
}

async function login() {
  username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value.trim();
  if (!username || !password)
    return showMessage("auth-message", "Vul gebruikersnaam en wachtwoord in");

  const res = await fetch("/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  const data = await res.json();
  if (res.ok) {
    startGame(data.floor);
  } else {
    showMessage("auth-message", data.error || "Login mislukt");
  }
}

function startGame(floor) {
  document.getElementById("auth").style.display = "none";
  document.getElementById("game").style.display = "block";
  showMessage("floor-info", `Verdieping: ${floor}`);
  socket.emit("register_user", { username });
  updateLeaderboard();
  updateActiveCount();
  const findBtn = document.getElementById("find-btn");
  if (findBtn) findBtn.disabled = false; // ⬅️ hier zorg je dat de knop pas actief is als spel gestart is
}

// 🕹️ Match zoeken
function findMatch() {
  if (!isConnected) {
    showMessage("result", "Geen verbinding met server. Ververs de pagina.");
    return;
  }

  if (currentOpponent !== null) {
    showMessage("result", "Je zit al in een match!");
    return;
  }

  if (!username) {
    showMessage("result", "Geen gebruiker ingelogd.");
    return;
  }

  showMessage("result", "");
  document.getElementById("battle").innerHTML = "";
  document.getElementById("find-btn").disabled = true; // 🔒 knop uit

  // Set timeout to re-enable button if no match found
  searchTimeout = setTimeout(() => {
    document.getElementById("find-btn").disabled = false;
    showMessage("result", "Geen tegenstander gevonden. Probeer opnieuw.");
  }, 30000); // 30 seconds timeout

  console.log(`🔍 ${username} searching for match...`);
  socket.emit("find_match", { username });
  showMessage("result", "Zoeken naar tegenstander...");
}

// 🪨📄✂️ Zet kiezen
function makeMove(move) {
  socket.emit("make_move", { username, move });
  document.getElementById(
    "battle"
  ).innerHTML = `<p>Je koos <strong>${move}</strong>. Wachten op tegenstander...</p>`;
}

// ✅ Accepteer match
function acceptMatch() {
  socket.emit("accept_match", { username });
}

// 👁️ Helper
function showMessage(id, text) {
  document.getElementById(id).innerText = text;
}

// 🎧 Socket events

// 🔌 Connection handling
socket.on("connect", () => {
  console.log("✅ Connected to server");
  isConnected = true;
  if (username) {
    console.log("🔄 Re-registering user after reconnect");
    socket.emit("register_user", { username });
  }
});

socket.on("disconnect", () => {
  console.log("❌ Disconnected from server");
  isConnected = false;
  showMessage("result", "Verbinding verbroken. Probeer opnieuw...");
});

socket.on("connected", (data) => {
  console.log("🔌 Server confirmed connection:", data);
});

socket.on("user_registered", (data) => {
  console.log("✅ User registration confirmed:", data);
});

socket.on("waiting", (data) => {
  showMessage("result", data.message);
});

socket.on("match_found", (data) => {
  // Clear search timeout since match was found
  if (searchTimeout) {
    clearTimeout(searchTimeout);
    searchTimeout = null;
  }

  currentOpponent = data.opponent;
  document.getElementById("battle").innerHTML = `
    <p>Gevonden tegenstander: <strong>${currentOpponent}</strong></p>
    <button onclick="acceptMatch()">✅ Accepteer Match</button>
  `;
  showMessage("result", "");
});

socket.on("waiting_accept", (data) => {
  showMessage("result", data.message);
});

socket.on("start_game", (data) => {
  showMessage("result", data.message);
  document.getElementById("battle").innerHTML = `
    <p>Kies je zet tegen <strong>${currentOpponent}</strong>:</p>
    <button onclick="makeMove('rock')">🪨 Rock</button>
    <button onclick="makeMove('paper')">📄 Paper</button>
    <button onclick="makeMove('scissors')">✂️ Scissors</button>
  `;
});

socket.on("waiting_move", (data) => {
  showMessage("result", data.message);
});

socket.on("game_result", (data) => {
  const { your_move, opponent_move, result, new_floor } = data;
  const resultText =
    {
      win: "🏆 Gewonnen!",
      lose: "❌ Verloren!",
      draw: "🤝 Gelijkspel!",
    }[result] || result;

  showMessage(
    "result",
    `
    Jij koos ${your_move}, ${currentOpponent} koos ${opponent_move}.
    Resultaat: ${resultText}
    Nieuwe verdieping: ${new_floor}
  `
  );

  showMessage("floor-info", `Verdieping: ${new_floor}`);
  document.getElementById("battle").innerHTML = "";
  document.getElementById("find-btn").disabled = false; // 🔓 knop weer aan
  currentOpponent = null;
});

socket.on("match_error", (data) => {
  showMessage("result", `❗ Fout: ${data.error}`);
});

function updateLeaderboard() {
  fetch("/leaderboard")
    .then((res) => res.json())
    .then((data) => {
      const html = data
        .map((entry, index) => {
          const statusIcon = entry.online ? "✅" : "🔴";
          return `
          <div>${index + 1}. ${statusIcon} <strong>${
            entry.username
          }</strong> - Verdieping ${entry.floor}</div>
        `;
        })
        .join("");
      document.getElementById("leaderboard").innerHTML = html;
    })
    .catch(() => {
      document.getElementById("leaderboard").innerText =
        "Kan leaderboard niet laden";
    });
}

function updateActiveCount() {
  fetch("/active_users")
    .then((res) => res.json())
    .then((data) => {
      document.getElementById("active-count").innerText = data.active;
    })
    .catch(() => {
      document.getElementById("active-count").innerText = "?";
    });
}

// 📊 Elke 5 seconden verversen
setInterval(updateLeaderboard, 2000);
setInterval(updateActiveCount, 2000);
