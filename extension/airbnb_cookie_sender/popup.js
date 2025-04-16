const sendBtn = document.getElementById("send");
const stopBtn = document.getElementById("stop");
const status = document.getElementById("status");

let isRunning = false;
const API_URL = "";

sendBtn.addEventListener("click", async () => {
  if (isRunning) return;
  status.textContent = "⏳ Подключение к вкладке...";

  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0];

    if (!tab || !tab.url.includes("airbnb.com")) {
      status.textContent = "⚠️ Перейди на airbnb.com и попробуй снова.";
      resetUI();
      return;
    }

    const debuggee = { tabId: tab.id };

    chrome.debugger.attach(debuggee, "1.3", () => {
      chrome.debugger.sendCommand(debuggee, "Network.getAllCookies", {}, async (result) => {
        chrome.debugger.detach(debuggee);

        const airbnbCookies = result.cookies.filter(cookie =>
          cookie.domain.includes("airbnb.com")
        );

        if (!airbnbCookies.length) {
          status.textContent = "❌ Не удалось найти cookies для airbnb.com";
          resetUI();
          return;
        }

        // Устанавливаем isRunning ТОЛЬКО когда начинаем отправку на сервер
        isRunning = true;

        try {
          const response = await fetch(`${API_URL}/api/save_cookies`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cookies: JSON.stringify(airbnbCookies) })
          });

          const json = await response.json();
          if (json.status === "ok") {
            status.textContent = `✅ Отправлено ${airbnbCookies.length} cookies!`;
          } else if (json.status === "already_running") {
            status.textContent = "⚠️ Автоответчик уже запущен.";
          } else {
            status.textContent = "❌ Ошибка: " + (json.detail || json.status);
          }

        } catch (e) {
            status.textContent = "🚫 Сетевая ошибка: " + e.message + "обратитесь к разработчику!";
        } finally {
          resetUI();
        }
      });
    });
  });
});

stopBtn.addEventListener("click", async () => {
  status.textContent = "⏳ Остановка автоответчика...";

  try {
    const response = await fetch(`${API_URL}/api/stop_scheduler`, {
      method: "POST"
    });

    const json = await response.json();
    if (json.status === "stopped") {
      status.textContent = "🛑 Остановлено пользователем.";
    } else if (json.status === "not_running") {
      status.textContent = "ℹ️ Автоответчик не был запущен.";
    } else {
      status.textContent = "❌ Не удалось остановить автоответчик.";
    }
  } catch (e) {
    status.textContent = "🚫 Сетевая ошибка: " + e.message + "обратитесь к разработчику!";
  } finally {
    resetUI();
  }
});

function resetUI() {
  isRunning = false;
}

document.getElementById("year").textContent = new Date().getFullYear();
