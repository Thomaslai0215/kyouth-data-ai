const chatHistory = document.getElementById("chat-history");
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const pdfInput = document.getElementById("pdf-input");
const uploadBtn = document.getElementById("upload-btn");

function appendMessage(role, text) {
  const wrapper = document.createElement("div");
  wrapper.className = `chat-message ${role === "user" ? "user-message" : "bot-message"}`;

  const body = document.createElement("div");
  body.className = "message-text";
  body.textContent = text;

  wrapper.appendChild(body);
  chatHistory.appendChild(wrapper);
  chatHistory.scrollTop = chatHistory.scrollHeight;
}

uploadBtn.addEventListener("click", () => {
  pdfInput.click();
});

async function extractPdfText(file) {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/api/pdf-to-text", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || "Could not extract text from the PDF.");
  }

  const data = await response.json();
  return data.pdf_text || "";
}

async function sendToBackend(message, pdfText) {
  if (!window.BACKEND_URL) {
    throw new Error("BACKEND_URL is not set. Add it to week3/.env");
  }

  const response = await fetch(window.BACKEND_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      pdf_text: pdfText,
    }),
  });

  if (!response.ok) {
    throw new Error(`Backend request failed with status ${response.status}`);
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const data = await response.json();
    return data.reply || data.message || JSON.stringify(data);
  }

  return await response.text();
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const message = messageInput.value.trim();
  const pdfFile = pdfInput.files[0];

  if (!message && !pdfFile) {
    return;
  }

  const displayMessage = message || "(PDF uploaded)";
  appendMessage("user", displayMessage);
  messageInput.value = "";

  try {
    let pdfText = "";
    if (pdfFile) {
      pdfText = await extractPdfText(pdfFile);
      pdfInput.value = "";
    }

    const reply = await sendToBackend(message, pdfText);
    appendMessage("bot", reply);
  } catch (error) {
    appendMessage("bot", error.message || "Something went wrong.");
  }
});
