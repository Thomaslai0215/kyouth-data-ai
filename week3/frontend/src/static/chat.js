const chatHistory = document.getElementById("chat-history");
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const pdfInput = document.getElementById("pdf-input");
const uploadBtn = document.getElementById("upload-btn");
const uploadStatus = document.getElementById("upload-status");
const resumeChip = document.getElementById("resume-chip");
const resumeChipName = document.getElementById("resume-chip-name");
const removeResumeBtn = document.getElementById("remove-resume-btn");
let uploadedPdfText = "";
let uploadedPdfName = "";

function setUploadStatus(text) {
  if (uploadStatus) {
    uploadStatus.textContent = text;
    uploadStatus.hidden = false;
  }
  if (resumeChip) {
    resumeChip.hidden = true;
  }
}

function showResumeChip(name) {
  uploadedPdfName = name;
  if (resumeChipName) {
    resumeChipName.textContent = name;
  }
  if (resumeChip) {
    resumeChip.hidden = false;
  }
  if (uploadStatus) {
    uploadStatus.hidden = true;
  }
}

function clearResume() {
  uploadedPdfText = "";
  uploadedPdfName = "";
  pdfInput.value = "";
  setUploadStatus("No resume uploaded yet.");
}

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

removeResumeBtn?.addEventListener("click", clearResume);

async function loadPdfFile(file) {
  setUploadStatus(`Reading ${file.name}...`);
  const pdfText = await extractPdfText(file);
  if (!pdfText.trim()) {
    throw new Error("Uploaded PDF has no readable text. Please use a text-based PDF.");
  }

  uploadedPdfText = pdfText;
  showResumeChip(file.name);
  appendMessage("user", `Uploaded resume: ${file.name}`);
  appendMessage(
    "bot",
    'Resume ready. Ask about your resume, or type "start analysis" / press Send for skill gaps.'
  );
}

pdfInput.addEventListener("change", async () => {
  const file = pdfInput.files[0];
  if (!file) {
    return;
  }

  try {
    await loadPdfFile(file);
  } catch (error) {
    clearResume();
    appendMessage("bot", error.message || "Could not process the uploaded PDF.");
  } finally {
    pdfInput.value = "";
  }
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

  if (!uploadedPdfText && pdfFile) {
    try {
      await loadPdfFile(pdfFile);
    } catch (error) {
      appendMessage("bot", error.message || "Could not process the uploaded PDF.");
      return;
    } finally {
      pdfInput.value = "";
    }
  }

  if (!message && !uploadedPdfText) {
    appendMessage("bot", "Type a message, or upload a resume PDF.");
    return;
  }

  const displayMessage = message || (uploadedPdfText ? "start analysis" : "");
  appendMessage("user", displayMessage);
  messageInput.value = "";

  try {
    const reply = await sendToBackend(message, uploadedPdfText);
    appendMessage("bot", reply);
  } catch (error) {
    appendMessage("bot", error.message || "Something went wrong.");
  }
});
