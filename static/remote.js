const powerButton = document.getElementById("power-button");
const bridgeStatus = document.getElementById("bridge-status");
const bridgeDot = document.getElementById("bridge-dot");
const commandStatus = document.getElementById("command-status");
const assistantAnswer = document.getElementById("assistant-answer");
const voiceButton = document.getElementById("voice-button");
const voiceForm = document.getElementById("voice-form");
const voiceInput = document.getElementById("voice-command");
const voiceHelp = document.getElementById("voice-help");
const tokenInput = document.getElementById("remote-token");
const saveToken = document.getElementById("save-token");

const TOKEN_KEY = "alfred-tv-remote-token";
tokenInput.value = window.localStorage.getItem(TOKEN_KEY) || "";

function remoteHeaders() {
  return {
    "Content-Type": "application/json",
    "X-Alfred-Remote": "1",
    "X-Alfred-Remote-Token": window.localStorage.getItem(TOKEN_KEY) || ""
  };
}

function setMessage(message, kind = "") {
  commandStatus.textContent = message;
  commandStatus.className = `command-status ${kind}`.trim();
}

async function checkBridge() {
  try {
    const response = await fetch("/api/tv/status", { cache: "no-store" });
    const data = await response.json();
    bridgeStatus.textContent = data.available ? "UNO Q connected" : data.message;
    bridgeDot.className = `status-dot ${data.available ? "ready" : "error"}`;
    powerButton.disabled = !data.available;
  } catch (error) {
    bridgeStatus.textContent = "Alfred is unreachable";
    bridgeDot.className = "status-dot error";
    powerButton.disabled = true;
  }
}

async function sendPower() {
  powerButton.disabled = true;
  setMessage("Sending Sony power signal…");
  try {
    const response = await fetch("/api/tv/power", {
      method: "POST",
      cache: "no-store",
      headers: remoteHeaders(),
      body: JSON.stringify({ action: "power" })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    setMessage(data.message || "Power signal sent.", "success");
    if (navigator.vibrate) navigator.vibrate(45);
  } catch (error) {
    setMessage(error.message, "error");
  } finally {
    window.setTimeout(checkBridge, 2100);
  }
}

async function askAlfred(query) {
  const trimmed = query.trim();
  if (!trimmed) {
    setMessage("Type or say a question first.", "error");
    return;
  }

  voiceInput.value = trimmed;
  voiceButton.disabled = true;
  assistantAnswer.textContent = "Thinking…";
  setMessage("");
  try {
    const response = await fetch("/api/assistant/query", {
      method: "POST",
      cache: "no-store",
      headers: remoteHeaders(),
      body: JSON.stringify({ query: trimmed })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
    assistantAnswer.textContent = data.answer;
    if (navigator.vibrate) navigator.vibrate(25);
  } catch (error) {
    assistantAnswer.textContent = "";
    setMessage(error.message, "error");
  } finally {
    voiceButton.disabled = false;
  }
}

powerButton.addEventListener("click", sendPower);

voiceForm.addEventListener("submit", (event) => {
  event.preventDefault();
  askAlfred(voiceInput.value);
});

saveToken.addEventListener("click", () => {
  window.localStorage.setItem(TOKEN_KEY, tokenInput.value.trim());
  setMessage("Access key saved on this phone.", "success");
});

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SpeechRecognition) {
  const recognition = new SpeechRecognition();
  recognition.lang = "en-US";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  voiceHelp.textContent = "Tap the microphone and ask about tasks, calendar, sleep, steps, heart rate, weather, or TV power.";

  voiceButton.addEventListener("click", () => {
    setMessage("Listening…");
    voiceButton.classList.add("listening");
    recognition.start();
  });
  recognition.addEventListener("result", (event) => {
    askAlfred(event.results[0][0].transcript);
  });
  recognition.addEventListener("error", (event) => {
    setMessage(`Voice recognition unavailable: ${event.error}. Use the Android app or keyboard microphone.`, "error");
  });
  recognition.addEventListener("end", () => {
    voiceButton.classList.remove("listening");
  });
} else {
  voiceButton.addEventListener("click", () => {
    voiceInput.focus();
    setMessage("Direct browser speech is unavailable here. Use the Android app or your keyboard microphone.", "error");
  });
}

checkBridge();
