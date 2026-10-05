"use strict";
const tg = window.Telegram?.WebApp;
const $ = id => document.getElementById(id);
const catalog = {
  community: [
    ["anon", "🕵", "Анонимка", "Мы передадим. Имя останется за кадром.", "#382a1c", "button1"],
    ["song", "♫", "Предложить песню", "Трек, который должен услышать клуб.", "#382a1c", "button2"],
    ["rate", "🎧", "Оценить трек", "Честное мнение о твоём исполнении.", "#382a1c", "button3"],
    ["day", "🎲", "Песня дня", "Открой что-нибудь неожиданное.", "#382a1c", "button4"],
    ["promo", "📣", "Промо", "Дай своему треку больше слушателей.", "#382a1c", "button6"],
    ["ask", "✧", "Спросить Ведьмака", "Задай вопрос нейросети.", "#382a1c"],
    ["draw", "✎", "Нарисовать картинку", "Опиши идею — нейросеть создаст изображение.", "#382a1c"],
    ["chat", "☏", "Поговорить с ботом", "Приветствия, беседы и немного настроения.", "#382a1c"],
  ],
  fun: [
    ["ded", "🧓", "Дедометр", "Общий градус ворчания во всех чатах.", "#382a1c"],
    ["guess", "♫", "Угадай песню", "Эмодзи вместо названия. Дед ждёт ответ.", "#382a1c"],
    ["mood", "🎭", "Настроение Ведьмака", "Выбери характер деда на час вместе с чатами.", "#382a1c"],
    ["prediction", "🔮", "Предсказание", "Что ждёт твой голос сегодня?", "#382a1c"],
    ["pole", "◎", "Поле чудес", "Буква за буквой — угадай слово.", "#382a1c"],
    ["casino", "🎰", "Казино", "Крути барабаны и лови удачу.", "#382a1c"],
    ["random", "♪", "Случайная песня", "Музыкальная находка из Last.fm.", "#382a1c"],
    ["cat", "🐈", "Котик", "Немного мурчания в твоём дне.", "#382a1c"],
    ["meme", "☺", "Мем", "Серьёзность подождёт.", "#382a1c"],
  ],
  social: [
    ["titles", "📜", "Геи и негры", "Общие итоги голосований во всех чатах.", "#382a1c"],
    ["passport", "🪪", "Паспорт сквада", "Один на всю жизнь. Дед подпись не меняет.", "#382a1c"],
    ["order", "🎖", "Твой орден", "Постоянная награда за вокальные подвиги.", "#382a1c"],
    ["halllist", "🏆", "Зал славы и позора", "Посмотри, о ком говорит клуб.", "#382a1c"],
    ["hall", "✦", "Номинация", "Кто заслужил место в истории?", "#382a1c"],
    ["vote", "✓", "Голосование", "Поддержи своего номинанта.", "#382a1c"],
  ],

};
const inputCommands = {
  ask: ["О чём спросим Ведьмака?", "Например: как перестать волноваться перед выступлением?"],
  draw: ["Какую картинку нарисовать?", "Например: кот с гитарой в золотом свете"],
  hall: ["Имя номинанта", "Никнейм участника"],
  vote: ["Имя номинанта", "Никнейм из зала славы или позора"],
};
const featureImages = {
  anon: "anon.png", song: "sing.png", rate: "rate.png", promo: "piar.png", ask: "ask.png",
  prediction: "prediction.png", pole: "pole.png", casino: "casino.png", halllist: "halllist.png",
  hall: "hall.png", vote: "vote.png", help: "help.png",
};
let current = null, data = {messages: []}, pending = false, authenticated = false;
const blobs = new Map();
const mediaJobs = new Map();
function notice(text) { $("notice").textContent = text; $("notice").hidden = !text; }
function theme() {
  document.documentElement.dataset.theme = "dark";
  tg?.setHeaderColor?.("#17110d");
  tg?.setBackgroundColor?.("#17110d");
}
theme();
tg?.ready(); tg?.expand(); tg?.onEvent("themeChanged", theme);
function api(path, options = {}) {
  return fetch(path, { ...options, headers: { "X-Telegram-Init-Data": tg?.initData || "", ...options.headers } }).then(async response => {
    if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(error.error || "Не удалось связаться с ботом"); }
    return response;
  });
}
function safeURL(value) {
  try { const url = new URL(value); return url.protocol === "https:" && !url.username && !url.password ? url.href : null; } catch { return null; }
}
function openLink(url) {
  const safe = safeURL(url); if (!safe) return;
  if (new URL(safe).hostname === "t.me" && tg?.initData) tg.openTelegramLink(safe);
  else if (tg?.initData) tg.openLink(safe);
  else window.open(safe, "_blank", "noopener,noreferrer");
}
function textContent(container, raw, mode) {
  // Telegram formatting is converted to text, never inserted into the live DOM.
  const clean = mode === "HTML" ? raw.replace(/<[^>]*>/g, "").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&") : raw.replace(/\*\*/g, "");
  for (const part of clean.split(/(https:\/\/[^\s<>]+)/g)) {
    if (part.startsWith("https://") && safeURL(part)) {
      const link = document.createElement("a"); link.href = part; link.textContent = part;
      link.addEventListener("click", event => { event.preventDefault(); openLink(part); }); container.append(link);
    } else container.append(document.createTextNode(part));
  }
}
async function mediaURL(key) {
  if (blobs.has(key)) return blobs.get(key);
  if (!mediaJobs.has(key)) mediaJobs.set(key, api(`/api/media/${encodeURIComponent(key)}`).then(r => r.blob()).then(blob => {
    const url = URL.createObjectURL(blob); blobs.set(key, url); mediaJobs.delete(key); return url;
  }).catch(error => { mediaJobs.delete(key); throw error; }));
  return mediaJobs.get(key);
}
function renderFeatureImage(force = false) {
  const image = $("feature-image"), filename = featureImages[current?.[0]];
  const hasPhoto = data.messages.some(m => m.kind === "photo" && (m.media || m.url));
  image.hidden = !filename || (hasPhoto && !force);
  if (filename) {
    image.src = `/assets/${filename}`; image.alt = current[2];
    image.onerror = () => { image.hidden = true; };
  } else image.removeAttribute("src");
}
function renderMessages() {
  const activeMedia = new Set(data.messages.map(m => m.media).filter(Boolean));
  for (const [key, url] of blobs) if (!activeMedia.has(key)) { URL.revokeObjectURL(url); blobs.delete(key); }
  $("messages").replaceChildren();
  for (const message of data.messages) {
    const card = document.createElement("article"); card.className = "message";
    if (message.author === "user") { card.classList.add("own-message"); const author = document.createElement("small"); author.textContent = "Вы"; card.append(author); }
    if (message.media || message.url) {
      const media = document.createElement(message.kind === "photo" ? "img" : "audio");
      if (message.kind === "photo") { media.alt = "Изображение от бота"; media.loading = "lazy"; } else media.controls = true;
      const unavailable = () => {
        if (!card.isConnected) return;
        media.remove(); const note = document.createElement("small");
        note.textContent = message.kind === "photo" ? "Не удалось загрузить изображение." : "Не удалось загрузить аудио.";
        card.prepend(note); if (message.kind === "photo") renderFeatureImage(true);
      };
      media.addEventListener("error", unavailable, {once: true});
      if (message.url && safeURL(message.url)) media.src = safeURL(message.url);
      else if (message.media) mediaURL(message.media).then(url => {
        if (media.isConnected) media.src = url;
        else if (!data.messages.some(m => m.media === message.media)) { URL.revokeObjectURL(url); blobs.delete(message.media); }
      }).catch(unavailable);
      card.append(media);
    }
    if (message.text) { const p = document.createElement("p"); textContent(p, message.text, message.parse_mode); card.append(p); }
    if (message.buttons) {
      const row = document.createElement("div"); row.className = "message-buttons";
      for (const button of message.buttons.flat()) {
        const control = document.createElement("button"); control.type = "button"; control.textContent = button.text;
        control.addEventListener("click", async () => {
          if (button.url) return openLink(button.url);
          if (!button.callback) return;
          await perform({action: "callback", callback: button.callback});
        }); row.append(control);
      } card.append(row);
    } $("messages").append(card);
  }
  renderFeatureImage();
  updateComposer();
}
function updateComposer() {
  const state = data.state || "";
  $("composer").hidden = !(state || data.playing || data.guessing || current?.[0] === "chat");
  $("command-form").hidden = !current || !inputCommands[current[0]];
  if (current && inputCommands[current[0]]) $("composer").hidden = true;
  $("attachments").hidden = state !== "anon_waiting_text";
  const labels = {
    anon_waiting_text: "Текст анонимки или подпись к вложению", song_waiting_text: "Название песни или ссылка",
    rate_waiting_link: "Ссылка на исполнение в Smule", promote_waiting_link: "Ссылка на трек",
  };
  $("composer-label").textContent = labels[state] || (data.guessing ? "Название песни" : data.playing ? "Буква или слово" : "Сообщение боту");
  $("quick-replies").replaceChildren();
}
function showHome(section = "home") {
  $("home").hidden = false; $("workspace").hidden = true; tg?.BackButton?.hide();
  document.querySelectorAll(".bottom-nav button").forEach(b => b.classList.toggle("active", b.dataset.section === section));
  if (section !== "home") $(section)?.scrollIntoView({behavior: "smooth", block: "start"}); else window.scrollTo({top: 0});
}
function showWorkspace(item) {
  current = item; $("home").hidden = true; $("workspace").hidden = false;
  $("workspace-title").textContent = item[2]; $("workspace-description").textContent = item[3];
  const input = inputCommands[item[0]];
  if (input) { $("command-label").textContent = input[0]; $("command-text").placeholder = input[1]; $("command-text").value = ""; $("command-text").required = true; }
  $("category").hidden = !["hall", "vote"].includes(item[0]);
  tg?.BackButton?.show(); window.scrollTo({top: 0}); renderMessages();
}
async function openItem(item) {
  if (pending) return;
  data = {...data, messages: [], state: null, playing: false, guessing: false};
  $("message-text").value = ""; $("file").value = ""; notice("");
  showWorkspace(item);
  if (!inputCommands[item[0]]) await perform(item[5] ? {action: "callback", callback: item[5]} : {action: "command", command: item[0]});
}
async function perform(body, file = null) {
  if (pending) return false;
  if (!authenticated) { notice("Откройте приложение кнопкой в чате с ботом, чтобы пользоваться функциями."); return false; }
  pending = true; $("busy").hidden = false; notice("");
  data = {...data, messages: []}; renderMessages();
  document.querySelectorAll("button").forEach(b => b.disabled = true);
  try {
    const requestId = crypto.randomUUID();
    let response;
    if (file) {
      const form = new FormData(); form.append("request_id", requestId); form.append("text", body.text || ""); form.append("kind", body.kind); form.append("file", file);
      response = await api("/api/upload", {method: "POST", body: form});
    } else response = await api("/api/action", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({...body, request_id: requestId})});
    data = await response.json(); renderMessages();
    $("messages").lastElementChild?.scrollIntoView({behavior: "smooth", block: "nearest"});
    tg?.HapticFeedback?.notificationOccurred("success"); return true;
  } catch (error) { notice(error.message); tg?.HapticFeedback?.notificationOccurred("error"); return false; }
  finally { pending = false; $("busy").hidden = true; document.querySelectorAll("button").forEach(b => b.disabled = false); }
}
for (const [section, items] of Object.entries(catalog)) for (const item of items) {
  const card = document.createElement("button"); card.type = "button"; card.className = "card";
  card.dataset.feature = item[0];
  const icon = document.createElement("span"); icon.className = "card-icon"; icon.textContent = item[1]; icon.style.setProperty("--tint", item[4]);
  const arrow = document.createElement("span"); arrow.className = "card-arrow"; arrow.textContent = "↗";
  const title = document.createElement("strong"); title.textContent = item[2];
  const description = document.createElement("small"); description.textContent = item[3];
  card.append(icon, arrow, title, description); card.addEventListener("click", () => openItem(item)); $(section).append(card);
}
$("command-form").addEventListener("submit", async event => {
  event.preventDefault(); let text = $("command-text").value.trim(); const command = current[0];
  if (["hall", "vote"].includes(command)) text = `${$("category").value} ${text}`;
  await perform({action: "command", command, text});
});
$("composer").addEventListener("submit", async event => {
  event.preventDefault(); const file = !$("attachments").hidden ? $("file").files[0] : null;
  const kind = file?.type.startsWith("image/") ? "photo" : $("file-kind").value;
  if (file && (file.size > (kind === "photo" ? 10 : 20) * 1024 * 1024)) return notice("Файл слишком большой: фото до 10 МБ, аудио до 20 МБ.");
  if (await perform({action: "message", text: $("message-text").value.trim(), kind}, file)) { $("message-text").value = ""; $("file").value = ""; }
});
$("file").addEventListener("change", () => { const file = $("file").files[0]; if (file) $("file-kind").value = file.type.startsWith("image/") ? "photo" : data.state === "anon_waiting_text" ? "voice" : "audio"; });
$("back").addEventListener("click", () => showHome()); tg?.BackButton?.onClick(() => showHome());
document.querySelector(".brand").addEventListener("click", event => { event.preventDefault(); showHome(); });
$("reset").addEventListener("click", async () => { if (await perform({action: "reset"})) showHome(); });
$("help").addEventListener("click", () => openItem(["help", "?", "Помощь", "Все возможности твоего музыкального клуба."]));
for (const link of document.querySelectorAll('a[href="https://dsipsmule.one"]')) {
  link.addEventListener("click", event => { event.preventDefault(); openLink(link.href); });
}
document.querySelectorAll(".bottom-nav button").forEach(b => b.addEventListener("click", () => showHome(b.dataset.section)));
async function boot() {
  if (!tg?.initData) return notice("Предпросмотр приложения. Для действий откройте его через Telegram-бота.");
  try {
    data = await (await api("/api/bootstrap")).json(); authenticated = true;
    $("greeting").textContent = `${data.user.first_name}, пой, делись и будь частью сообщества.`;
    $("avatar").textContent = data.user.first_name.slice(0, 1).toUpperCase();
    if (data.state || data.playing || data.guessing) showWorkspace(["resume", "", "Продолжить", "Твой незавершённый контракт. Продолжи с текущего шага."]);
  } catch (error) { notice(error.message); }
}
boot();
