(function () {
  "use strict";

  var LETTERS = ["A", "B", "C", "D"];
  var MAX_UPLOAD_MB = 15;

  var $ = function (id) { return document.getElementById(id); };
  var els = {
    form: $("genForm"), dropzone: $("dropzone"), fileInput: $("fileInput"), fileChip: $("fileChip"),
    fileName: $("fileName"), fileSize: $("fileSize"), removeFile: $("removeFile"),
    pasteBox: $("pasteBox"), pasteText: $("pasteText"),
    num: $("numQuestions"), numOut: $("numOut"), topic: $("topic"),
    allowWeb: $("allowWeb"), maxWeb: $("maxWeb"), webOut: $("webOut"), webCountField: $("webCountField"),
    generateBtn: $("generateBtn"), configWarning: $("configWarning"), modeBadge: $("modeBadge"),
    themeToggle: $("themeToggle"), workspace: $("workspace"),
    empty: $("emptyState"), loading: $("loadingState"), elapsed: $("elapsed"),
    errorBox: $("errorState"), errorTitle: $("errorTitle"), errorMessage: $("errorMessage"),
    results: $("results"), resultsTitle: $("resultsTitle"), resultsSub: $("resultsSub"),
    report: $("report"), reportNote: $("reportNote"), sourcesBox: $("sourcesBox"), sourcesList: $("sourcesList"),
    tabReview: $("tabReview"), tabQuiz: $("tabQuiz"), reviewPanel: $("reviewPanel"), quizPanel: $("quizPanel"),
    exportTxt: $("exportTxt"), exportJson: $("exportJson"), printBtn: $("printBtn"), toast: $("toast")
  };

  var state = { file: null, config: null, result: null, answers: {}, graded: false, timer: null, toastTimer: null };

  /* ---------- small helpers ---------- */
  function h(tag, props) {
    var el = document.createElement(tag);
    props = props || {};
    Object.keys(props).forEach(function (k) {
      var v = props[k];
      if (v === null || v === undefined || v === false) return;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.indexOf("on") === 0 && typeof v === "function") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    });
    for (var i = 2; i < arguments.length; i++) append(el, arguments[i]);
    return el;
  }
  function append(el, kid) {
    if (kid === null || kid === undefined || kid === false) return;
    if (Array.isArray(kid)) { kid.forEach(function (k) { append(el, k); }); return; }
    el.appendChild(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); }

  function formatBytes(n) {
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / (1024 * 1024)).toFixed(1) + " MB";
  }

  function toast(message) {
    els.toast.textContent = message;
    els.toast.hidden = false;
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(function () { els.toast.hidden = true; }, 3200);
  }

  function show(which) {
    els.empty.hidden = which !== "empty";
    els.loading.hidden = which !== "loading";
    els.errorBox.hidden = which !== "error";
    els.results.hidden = which !== "results";
  }

  /* ---------- theme ---------- */
  function effectiveTheme() {
    var attr = document.documentElement.getAttribute("data-theme");
    if (attr === "light" || attr === "dark") return attr;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function syncThemeButton() {
    els.themeToggle.textContent = effectiveTheme() === "dark" ? "Switch to light theme" : "Switch to dark theme";
  }
  els.themeToggle.addEventListener("click", function () {
    var next = effectiveTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("mcq-theme", next); } catch (e) { /* storage unavailable */ }
    syncThemeButton();
  });
  syncThemeButton();
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    var onSchemeChange = function () { syncThemeButton(); };
    if (mq.addEventListener) mq.addEventListener("change", onSchemeChange);
  }

  /* ---------- config ---------- */
  fetch("/api/config").then(function (r) { return r.json(); }).then(function (cfg) {
    state.config = cfg;
    if (cfg.demo_mode) {
      els.modeBadge.textContent = "Demo mode: simple offline questions, no AI";
      els.modeBadge.hidden = false;
    } else if (!cfg.has_api_key) {
      els.configWarning.textContent = "No Gemini API key found. Add GOOGLE_API_KEY to your .env file and restart the server, or set DEMO_MODE=1 to try the interface without one.";
      els.configWarning.hidden = false;
    }
  }).catch(function () {
    els.configWarning.textContent = "Can't reach the server. Start it with python server.py, then reload this page.";
    els.configWarning.hidden = false;
  });

  /* ---------- settings ---------- */
  els.num.addEventListener("input", function () { els.numOut.textContent = els.num.value; });
  els.maxWeb.addEventListener("input", function () { els.webOut.textContent = els.maxWeb.value; });
  function syncWeb() { els.maxWeb.disabled = !els.allowWeb.checked; els.webCountField.style.opacity = els.allowWeb.checked ? "1" : "0.5"; }
  els.allowWeb.addEventListener("change", syncWeb);
  syncWeb();

  /* ---------- file selection ---------- */
  function setFile(file) {
    if (!file) return;
    var ext = (file.name.split(".").pop() || "").toLowerCase();
    if (ext !== "pdf" && ext !== "txt") {
      toast("Upload a PDF or TXT file.");
      return;
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      toast("That file is over " + MAX_UPLOAD_MB + " MB. Upload a smaller one.");
      return;
    }
    state.file = file;
    els.fileName.textContent = file.name;
    els.fileSize.textContent = formatBytes(file.size);
    els.fileChip.hidden = false;
  }
  function removeFile() {
    state.file = null;
    els.fileInput.value = "";
    els.fileChip.hidden = true;
  }
  els.dropzone.addEventListener("click", function () { els.fileInput.click(); });
  els.dropzone.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); els.fileInput.click(); }
  });
  els.fileInput.addEventListener("change", function () { setFile(els.fileInput.files[0]); });
  els.removeFile.addEventListener("click", removeFile);
  ["dragenter", "dragover"].forEach(function (t) {
    els.dropzone.addEventListener(t, function (e) { e.preventDefault(); els.dropzone.classList.add("is-over"); });
  });
  ["dragleave", "drop"].forEach(function (t) {
    els.dropzone.addEventListener(t, function (e) { e.preventDefault(); els.dropzone.classList.remove("is-over"); });
  });
  els.dropzone.addEventListener("drop", function (e) {
    if (e.dataTransfer && e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
  });

  /* ---------- generate ---------- */
  function showError(title, message) {
    els.errorTitle.textContent = title;
    els.errorMessage.textContent = message;
    show("error");
    els.workspace.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function startTimer() {
    var t0 = Date.now();
    els.elapsed.textContent = "0s";
    state.timer = setInterval(function () {
      els.elapsed.textContent = Math.round((Date.now() - t0) / 1000) + "s";
    }, 500);
  }
  function stopTimer() { clearInterval(state.timer); state.timer = null; }

  els.form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = els.pasteText.value.trim();
    if (!state.file && !text) {
      showError("Add your notes first", "Upload a PDF or TXT file, or paste your notes, then choose Generate questions.");
      return;
    }

    var body = new FormData();
    if (state.file) body.append("file", state.file, state.file.name);
    else body.append("text", text);
    body.append("num_questions", els.num.value);
    body.append("topic", els.topic.value.trim());
    body.append("allow_web", els.allowWeb.checked ? "1" : "0");
    body.append("max_web_results", els.maxWeb.value);

    els.generateBtn.disabled = true;
    els.generateBtn.textContent = "Generating…";
    show("loading");
    startTimer();

    var controller = new AbortController();
    var abortTimer = setTimeout(function () { controller.abort(); }, 180000);

    fetch("/api/generate", { method: "POST", body: body, signal: controller.signal })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) { return { ok: res.ok, data: data }; });
      })
      .then(function (out) {
        if (!out.ok) {
          showError("Couldn't generate questions", out.data.message || "The server returned an unexpected reply. Try again.");
          return;
        }
        state.result = out.data;
        renderResults();
        toast("Generated " + out.data.questions.length + (out.data.questions.length === 1 ? " question" : " questions"));
      })
      .catch(function (err) {
        if (err && err.name === "AbortError") {
          showError("This is taking too long", "The request timed out after 3 minutes. Try fewer questions or shorter notes.");
        } else {
          showError("Can't reach the server", "Check that python server.py is still running, then try again.");
        }
      })
      .then(function () {
        clearTimeout(abortTimer);
        stopTimer();
        els.generateBtn.disabled = false;
        els.generateBtn.textContent = "Generate questions";
      });
  });

  /* ---------- rendering ---------- */
  function bubble(letter, filled) {
    return h("span", { class: "bubble" + (filled ? " is-filled" : ""), "aria-hidden": "true" }, letter);
  }

  function difficultyBadge(fuzzy) {
    var level = { Easy: 1, Medium: 2, Hard: 3 }[fuzzy.difficulty] || 2;
    var segs = h("span", { class: "diff-segs", "aria-hidden": "true" },
      [1, 2, 3].map(function (i) { return h("i", { class: i <= level ? "on" : "" }); }));
    return h("span", { class: "diff" }, segs, fuzzy.difficulty);
  }

  function meterRow(label, value, suffix) {
    var bar = h("span", { class: "meter", role: "meter", "aria-label": label, "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(value) },
      h("span"));
    bar.firstChild.style.width = Math.max(0, Math.min(100, value)) + "%";
    return h("div", { class: "assess-row" },
      h("span", { class: "assess-label" }, label), bar, h("span", { class: "assess-val" }, value + (suffix || "")));
  }

  function renderResults() {
    var r = state.result, meta = r.meta, qs = r.questions;
    state.answers = {};
    state.graded = false;

    els.resultsTitle.textContent = qs.length + (qs.length === 1 ? " question" : " questions") + " from your notes";
    var sub = meta.source_name + " • " + meta.notes_chars.toLocaleString() + " characters read" +
      (meta.topic ? " • focus: " + meta.topic : "") + " • " + meta.seconds + "s";
    els.resultsSub.textContent = sub;

    clear(els.report);
    [
      ["Passages used", meta.passages_used + " of " + meta.note_chunks],
      ["Correction attempts", String(meta.attempts)],
      ["Web fallback", meta.used_web ? "Used" : "Not needed"]
    ].forEach(function (row) {
      els.report.appendChild(h("div", null, h("dt", null, row[0]), h("dd", null, row[1])));
    });

    var note = meta.retrieval_note || "";
    if (meta.truncated) note += " Only the first " + meta.max_input_chars.toLocaleString() + " characters of your notes were used.";
    if (meta.demo) note += " Demo mode: these questions were built with simple text rules, not AI.";
    els.reportNote.textContent = note.trim();

    clear(els.sourcesList);
    (meta.sources || []).forEach(function (s) {
      var isUrl = /^https?:\/\//i.test(s);
      els.sourcesList.appendChild(h("li", null,
        isUrl ? h("a", { href: s, target: "_blank", rel: "noopener noreferrer" }, s) : s));
    });
    els.sourcesBox.hidden = !(meta.sources && meta.sources.length);

    renderReview();
    renderQuiz();
    selectTab("review");
    show("results");
    els.workspace.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderReview() {
    clear(els.reviewPanel);
    var list = h("ol", { class: "q-list" });
    state.result.questions.forEach(function (q, idx) {
      var f = q.fuzzy;
      var opts = h("ul", { class: "opts" }, q.options.map(function (opt, i) {
        var correct = opt === q.correct_answer;
        return h("li", { class: "opt-row" + (correct ? " is-correct" : "") },
          bubble(LETTERS[i], correct),
          h("span", { class: "opt-text" }, opt, correct ? h("span", { class: "tag tag-good" }, "Correct answer") : null));
      }));

      var assess = h("div", { class: "assess" },
        h("div", { class: "assess-row" }, h("span", { class: "assess-label" }, "Difficulty"), difficultyBadge(f),
          h("span", { class: "assess-val" }, f.difficulty_score + "/100")),
        meterRow("Quality", f.quality_score, "/100"),
        meterRow("Evidence coverage", f.evidence_coverage, "/100"),
        f.flags.length
          ? h("ul", { class: "flags" }, f.flags.map(function (t) { return h("li", null, t); }))
          : h("p", { class: "no-flags" }, "No quality flags raised."));

      list.appendChild(h("li", { class: "q" },
        h("div", { class: "q-num", "aria-hidden": "true" }, String(idx + 1)),
        h("div", { class: "q-body" },
          h("p", { class: "q-text" }, h("span", { class: "sr-only" }, "Question " + (idx + 1) + ". "), q.question),
          opts,
          q.explanation ? h("p", { class: "explain" }, h("strong", null, "Why: "), q.explanation) : null,
          assess)));
    });
    els.reviewPanel.appendChild(list);
    els.reviewPanel.appendChild(h("p", { class: "note-small" },
      "Difficulty and quality come from fuzzy-logic rules over wording, option similarity and overlap with your notes. They are estimates, not proof that an answer is factually correct."));
  }

  /* ---------- quiz ---------- */
  function answeredCount() { return Object.keys(state.answers).length; }

  function updateQuizBar() {
    var total = state.result.questions.length, n = answeredCount();
    var label = $("quizProgressLabel");
    if (!label) return;
    label.textContent = n + " of " + total + " answered";
    var meter = $("quizMeter");
    meter.firstChild.style.width = (100 * n / total) + "%";
    meter.setAttribute("aria-valuenow", String(n));
  }

  function renderQuiz() {
    clear(els.quizPanel);
    state.answers = {};
    state.graded = false;
    var qs = state.result.questions;

    var meter = h("span", { class: "meter", id: "quizMeter", role: "meter", "aria-label": "Questions answered", "aria-valuemin": "0", "aria-valuemax": String(qs.length), "aria-valuenow": "0" }, h("span"));
    var submit = h("button", { type: "button", class: "primary-btn", id: "submitQuiz", onclick: gradeQuiz }, "Submit answers");
    els.quizPanel.appendChild(h("div", { class: "quiz-bar" }, h("span", { id: "quizProgressLabel" }, "0 of " + qs.length + " answered"), meter, submit));
    els.quizPanel.appendChild(h("div", { id: "scoreSlot" }));

    var list = h("ol", { class: "q-list quiz-list", id: "quizList" });
    qs.forEach(function (q, idx) {
      var name = "quiz-q" + q.id;
      var picks = h("div", { class: "opts" }, q.options.map(function (opt, i) {
        var input = h("input", { type: "radio", name: name, value: String(i) });
        input.addEventListener("change", function () { state.answers[q.id] = opt; updateQuizBar(); });
        return h("label", { class: "pick", "data-option": String(i) }, input, bubble(LETTERS[i], false), h("span", { class: "opt-text" }, opt));
      }));
      list.appendChild(h("li", { class: "q", "data-qid": String(q.id) },
        h("div", { class: "q-num", "aria-hidden": "true" }, String(idx + 1)),
        h("fieldset", { class: "q-body", style: "border:0;padding:0;margin:0;min-width:0" },
          h("legend", { class: "q-text", style: "padding:0" }, h("span", { class: "sr-only" }, "Question " + (idx + 1) + ". "), q.question),
          picks)));
    });
    els.quizPanel.appendChild(list);
  }

  function gradeQuiz() {
    if (state.graded) return;
    var qs = state.result.questions;
    var unanswered = qs.length - answeredCount();
    if (unanswered > 0 && !window.confirm(unanswered + (unanswered === 1 ? " question is" : " questions are") + " unanswered. Submit anyway?")) return;

    state.graded = true;
    var score = 0;
    var list = $("quizList");
    list.classList.add("is-graded");

    qs.forEach(function (q) {
      var li = list.querySelector('[data-qid="' + q.id + '"]');
      var chosen = state.answers[q.id];
      if (chosen === q.correct_answer) score++;

      li.querySelectorAll("input").forEach(function (inp) { inp.disabled = true; });
      li.querySelectorAll(".pick").forEach(function (pick, i) {
        var opt = q.options[i];
        var text = pick.querySelector(".opt-text");
        if (opt === q.correct_answer) {
          pick.classList.add("is-correct");
          pick.querySelector(".bubble").classList.add("is-filled");
          text.appendChild(h("span", { class: "tag tag-good" }, chosen === opt ? "Correct, your answer" : "Correct answer"));
        } else if (opt === chosen) {
          pick.classList.add("is-wrong");
          text.appendChild(h("span", { class: "tag tag-bad" }, "Your answer"));
        }
      });

      var body = li.querySelector(".q-body");
      if (chosen === undefined) body.appendChild(h("p", { class: "explain" }, h("span", { class: "tag tag-bad", style: "margin-left:0" }, "Not answered")));
      if (q.explanation) body.appendChild(h("p", { class: "explain" }, h("strong", null, "Why: "), q.explanation));
    });

    var pct = Math.round(100 * score / qs.length);
    var card = h("div", { class: "score-card" },
      h("h3", null, "You scored " + score + " of " + qs.length),
      h("span", { class: "meter", role: "meter", "aria-label": "Score", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(pct) }, h("span")),
      h("p", null, pct + "% correct"),
      h("div", { class: "score-actions" },
        h("button", { type: "button", class: "ghost-btn", onclick: function () { renderQuiz(); els.quizPanel.scrollIntoView({ behavior: "smooth" }); } }, "Retake the quiz"),
        h("button", { type: "button", class: "ghost-btn", onclick: function () { selectTab("review"); } }, "Back to review")));
    card.querySelector(".meter > span").style.width = pct + "%";
    var slot = $("scoreSlot");
    clear(slot);
    slot.appendChild(card);
    $("submitQuiz").disabled = true;
    card.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  /* ---------- tabs ---------- */
  function selectTab(which) {
    var review = which === "review";
    els.tabReview.setAttribute("aria-selected", review ? "true" : "false");
    els.tabQuiz.setAttribute("aria-selected", review ? "false" : "true");
    els.tabReview.tabIndex = review ? 0 : -1;
    els.tabQuiz.tabIndex = review ? -1 : 0;
    els.reviewPanel.hidden = !review;
    els.quizPanel.hidden = review;
  }
  els.tabReview.addEventListener("click", function () { selectTab("review"); });
  els.tabQuiz.addEventListener("click", function () { selectTab("quiz"); });
  [els.tabReview, els.tabQuiz].forEach(function (tab) {
    tab.addEventListener("keydown", function (e) {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        var toQuiz = tab === els.tabReview;
        selectTab(toQuiz ? "quiz" : "review");
        (toQuiz ? els.tabQuiz : els.tabReview).focus();
      }
    });
  });

  /* ---------- export ---------- */
  function download(filename, mime, content) {
    var blob = new Blob([content], { type: mime });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  els.exportTxt.addEventListener("click", function () {
    if (!state.result) return;
    var text = state.result.questions.map(function (q, i) {
      var f = q.fuzzy;
      return "Q" + (i + 1) + ". " + q.question + "\n" +
        q.options.map(function (o, j) { return "  " + LETTERS[j] + ". " + o; }).join("\n") +
        "\nCorrect answer: " + q.correct_answer +
        (q.explanation ? "\nWhy: " + q.explanation : "") +
        "\nDifficulty: " + f.difficulty + " (" + f.difficulty_score + "/100)" +
        "\nQuality score: " + f.quality_score + "/100" +
        "\nEvidence coverage: " + f.evidence_coverage + "/100" +
        "\nFlags: " + (f.flags.length ? f.flags.join("; ") : "None");
    }).join("\n\n");
    download("mcqs.txt", "text/plain;charset=utf-8", text + "\n");
  });
  els.exportJson.addEventListener("click", function () {
    if (!state.result) return;
    download("mcqs.json", "application/json", JSON.stringify(state.result, null, 2));
  });
  els.printBtn.addEventListener("click", function () {
    selectTab("review");
    window.print();
  });
})();
