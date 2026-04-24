"use strict";

const SERVER_URL = "http://localhost:8000";
const DOWNLOAD_ENDPOINT = SERVER_URL + "/add-download";
const DOWNLOAD_MESSAGE = "QUEUE_DEVICE_DOWNLOAD";
const REQUEST_TIMEOUT_MS = 10000;

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== DOWNLOAD_MESSAGE) {
    return false;
  }

  queueDownload(message.payload)
    .then((result) => {
      sendResponse({
        ok: true,
        taskId: result.task_id || null,
        message: result.message || "Download queued successfully.",
      });
    })
    .catch((error) => {
      sendResponse({
        ok: false,
        error: normalizeError(error),
      });
    });

  return true;
});

async function queueDownload(payload) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(DOWNLOAD_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
      signal: controller.signal,
    });

    const data = await response.json().catch(() => null);

    if (!response.ok) {
      throw new Error(readErrorMessage(data, response.status));
    }

    return data || {};
  } finally {
    clearTimeout(timeoutId);
  }
}

function readErrorMessage(data, statusCode) {
  if (data && typeof data.detail === "string" && data.detail.trim()) {
    return data.detail.trim();
  }
  if (data && typeof data.message === "string" && data.message.trim()) {
    return data.message.trim();
  }
  return "PyFlow server error (" + statusCode + ").";
}

function normalizeError(error) {
  if (error && error.name === "AbortError") {
    return "Request timed out. Make sure the PyFlow server is running.";
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return "Unable to reach the PyFlow server.";
}
