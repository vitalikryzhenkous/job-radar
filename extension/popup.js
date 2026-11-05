// Job Radar: ссылки на вакансии с открытой вкладки -> локальный jr serve (/api/collect) -> оценка -> карта.
// Страницы вакансий качает сервер (пауза 2 с, robots.txt проверен), расширение только собирает ссылки.
const API = "http://127.0.0.1:8766";
const MAX = 100;                                   // = scan.MAX_COLLECT
const DEC_RU = { apply: "подаваться", clarify: "уточнить", skip: "пропустить", duplicate: "дубль", stop_scam: "скам" };
const $ = s => document.querySelector(s);
const say = (text, cls = "") => { $("#msg").className = cls; $("#msg").textContent = text; };
const button = (text, fn, cls = "") => {
  const b = document.createElement("button"); b.textContent = text; b.className = cls; b.onclick = fn;
  $("#actions").append(b); return b;
};
const clean = u => u.split("#")[0].split("?")[0].replace(/\/$/, "");

async function getJSON(path, opts) {
  const r = await fetch(API + path, opts);
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.status);
  return j;
}

function matches(u, sites) {
  try {
    const x = new URL(u);
    const rx = sites[x.hostname];
    return x.protocol === "https:" && !!rx && new RegExp("^" + rx + "$").test(x.pathname.replace(/\/$/, ""));
  } catch { return false; }
}

async function main() {
  let sites;
  try { sites = await getJSON("/api/sites"); }
  catch { return say("jr serve не запущен. В WSL: jr serve", "err"); }

  const st = await getJSON("/api/job");
  if (st.running) return poll();

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const host = new URL(tab.url || "about:blank").hostname;
  if (/(^|\.)linkedin\.com$/.test(host))
    return say("LinkedIn массово не собираем: похоже на автоматизацию, риск блокировки аккаунта. Вакансию — вставкой: jr add.", "err");

  let links = [];
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => [...document.querySelectorAll("a[href]")].map(a => a.href),   // только чтение ссылок, страницу не меняем
    });
    links = result;
  } catch { return say("На этой вкладке нельзя читать страницу (служебная страница браузера?).", "err"); }

  const urls = [...new Set(links.map(clean).filter(u => matches(u, sites)))];
  if (!urls.length)
    return say(`Ссылок на вакансии не нашёл. Площадки: ${Object.keys(sites).join(", ")}.`, "err");
  const send = urls.slice(0, MAX);
  say(`Найдено вакансий: ${urls.length}${urls.length > MAX ? ` (за раз беру первые ${MAX})` : ""}.`
      + " Списки подгружаются при прокрутке: прокрути до конца, чтобы взять больше, и открой окно снова.");
  const go = button(`Оценить ${send.length}`, async e => {
    e.target.disabled = true;
    try { await getJSON("/api/collect", { method: "POST", headers: { "Content-Type": "application/json" },
                                          body: JSON.stringify({ urls: send }) }); poll(); }
    catch (err) { say("Сервер отказал: " + err.message, "err"); e.target.disabled = false; }
  }, "main");
  go.focus();
}

async function poll() {
  $("#actions").replaceChildren();
  const st = await getJSON("/api/job");
  const m = [...st.log].reverse().map(l => /^\[(\d+)\/(\d+)\]/.exec(l)).find(Boolean);   // «[12/50] apply …»
  const bar = $("#bar"); bar.hidden = !st.running;
  if (st.running) {
    bar.classList.toggle("wait", !m);                                  // ещё нет «[n/N]» — бегущие блоки
    $("#fill").style.width = m ? `${Math.round(100 * m[1] / m[2])}%` : "";
    say(m ? `Оцениваю ${m[1]} из ${m[2]} · осталось ~${Math.ceil((m[2] - m[1]) * 2 / 60)} мин. Окно можно закрыть — работа идёт на сервере.`
          : "Начинаю…");
    return setTimeout(poll, 1500);
  }
  if (st.error) return say("Ошибка: " + st.error, "err");
  say(`Готово. Пул ${st.pool}:`);
  const order = ["apply", "clarify", "skip"];                         // сначала то, что важно, затем остальное
  const rows = Object.entries(st.summary || {}).sort(([a], [b]) => (order.indexOf(a) + 9) % 9 - (order.indexOf(b) + 9) % 9);
  $("#stats").replaceChildren(...rows.map(([k, v]) => {
    const li = document.createElement("li"); li.className = order.includes(k) ? k : "other";
    li.innerHTML = '<span class="lbl"></span><span class="dots"></span><b></b>';
    li.querySelector(".lbl").textContent = DEC_RU[k] || k; li.querySelector("b").textContent = v;
    return li;
  }));
  $("#stats").hidden = !rows.length;
  button("Ещё раз", () => location.reload());
  button("Открыть карту", () => chrome.tabs.create({ url: API + "/" }), "main").focus();
}

main().catch(e => say("Ошибка: " + e.message, "err"));
