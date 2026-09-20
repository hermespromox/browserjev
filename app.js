(() => {
  "use strict";

  const MAX_QUESTIONS = 8;
  let nextId = 1;
  let questions = [];

  const form = document.querySelector("#analysis-form");
  const targetInput = document.querySelector("#target");
  const questionsRoot = document.querySelector("#questions");
  const addQuestionButton = document.querySelector("#add-question");
  const submitButton = document.querySelector("#submit-button");
  const formError = document.querySelector("#form-error");
  const loadingPanel = document.querySelector("#loading");
  const resultsPanel = document.querySelector("#results");
  const answersRoot = document.querySelector("#answers");
  const evidenceRoot = document.querySelector("#evidence");
  const summaryRoot = document.querySelector("#result-summary");
  const evidenceCount = document.querySelector("#evidence-count");
  const newAnalysisButton = document.querySelector("#new-analysis");

  function createQuestion(type = "noul") {
    return {
      id: nextId++,
      type,
      instructions: "",
      options: [
        { value: "option_1", description: "" },
        { value: "option_2", description: "" },
      ],
      levels: ["Faible", "Moyen", "Élevé"],
    };
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function field(labelText, input) {
    const wrapper = el("div", "field");
    const label = el("label", "field-label", labelText);
    label.htmlFor = input.id;
    wrapper.append(label, input);
    return wrapper;
  }

  function textInput({ id, value, placeholder, maxLength = 240 }) {
    const input = document.createElement("input");
    input.type = "text";
    input.id = id;
    input.value = value;
    input.placeholder = placeholder;
    input.maxLength = maxLength;
    return input;
  }

  function iconButton(label, disabled, onClick) {
    const button = el("button", "icon-button", "×");
    button.type = "button";
    button.setAttribute("aria-label", label);
    button.title = label;
    button.disabled = disabled;
    button.addEventListener("click", onClick);
    return button;
  }

  function renderChoiceDetails(question) {
    const details = el("div", "type-details");
    const header = el("div", "type-details-header");
    header.append(
      el("p", "", "Chaque valeur doit être unique. Jev choisira une seule option."),
    );
    const addOption = el("button", "small-action", "＋ Ajouter une option");
    addOption.type = "button";
    addOption.disabled = question.options.length >= 10;
    addOption.addEventListener("click", () => {
      question.options.push({
        value: `option_${question.options.length + 1}`,
        description: "",
      });
      renderQuestions();
    });
    header.append(addOption);
    details.append(header);

    question.options.forEach((option, optionIndex) => {
      const row = el("div", "option-row");
      const valueInput = textInput({
        id: `q-${question.id}-option-${optionIndex}-value`,
        value: option.value,
        placeholder: "ex. logiciel",
        maxLength: 60,
      });
      valueInput.addEventListener("input", (event) => {
        option.value = event.target.value;
      });
      const descriptionInput = textInput({
        id: `q-${question.id}-option-${optionIndex}-description`,
        value: option.description,
        placeholder: "Description de cette option",
      });
      descriptionInput.addEventListener("input", (event) => {
        option.description = event.target.value;
      });
      row.append(
        field("Valeur", valueInput),
        field("Description", descriptionInput),
        iconButton("Supprimer cette option", question.options.length <= 2, () => {
          question.options.splice(optionIndex, 1);
          renderQuestions();
        }),
      );
      details.append(row);
    });
    return details;
  }

  function renderScoreDetails(question) {
    const details = el("div", "type-details");
    const header = el("div", "type-details-header");
    header.append(el("p", "", "Les niveaux sont transmis à Jev dans cet ordre."));
    const addLevel = el("button", "small-action", "＋ Ajouter un niveau");
    addLevel.type = "button";
    addLevel.disabled = question.levels.length >= 10;
    addLevel.addEventListener("click", () => {
      question.levels.push(`Niveau ${question.levels.length + 1}`);
      renderQuestions();
    });
    header.append(addLevel);
    details.append(header);

    question.levels.forEach((level, levelIndex) => {
      const row = el("div", "level-row");
      const levelInput = textInput({
        id: `q-${question.id}-level-${levelIndex}`,
        value: level,
        placeholder: "Nom du niveau",
        maxLength: 120,
      });
      levelInput.addEventListener("input", (event) => {
        question.levels[levelIndex] = event.target.value;
      });
      row.append(
        field(`Niveau ${levelIndex + 1}`, levelInput),
        iconButton("Supprimer ce niveau", question.levels.length <= 2, () => {
          question.levels.splice(levelIndex, 1);
          renderQuestions();
        }),
      );
      details.append(row);
    });
    return details;
  }

  function renderQuestion(question, index) {
    const card = el("article", "question-card");
    const indexPanel = el("div", "question-index");
    indexPanel.append(el("strong", "", `Q${String(index + 1).padStart(2, "0")}`));
    const remove = el("button", "remove-question", "Supprimer");
    remove.type = "button";
    remove.disabled = questions.length === 1;
    remove.addEventListener("click", () => {
      questions = questions.filter((item) => item.id !== question.id);
      renderQuestions();
    });
    indexPanel.append(remove);

    const content = el("div", "question-content");
    const mainFields = el("div", "question-main-fields");

    const typeSelect = document.createElement("select");
    typeSelect.id = `q-${question.id}-type`;
    [
      ["noul", "Oui / Non (Noul)"],
      ["choice", "Choix unique"],
      ["score", "Score"],
    ].forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      option.selected = value === question.type;
      typeSelect.append(option);
    });
    typeSelect.addEventListener("change", (event) => {
      question.type = event.target.value;
      renderQuestions();
    });

    const instructionInput = textInput({
      id: `q-${question.id}-instructions`,
      value: question.instructions,
      placeholder: "Ex. Le site affiche-t-il des tarifs précis ?",
      maxLength: 500,
    });
    instructionInput.addEventListener("input", (event) => {
      question.instructions = event.target.value;
    });

    mainFields.append(field("Type de réponse", typeSelect), field("Question / instruction", instructionInput));
    content.append(mainFields);

    if (question.type === "choice") content.append(renderChoiceDetails(question));
    if (question.type === "score") content.append(renderScoreDetails(question));

    card.append(indexPanel, content);
    return card;
  }

  function renderQuestions() {
    questionsRoot.replaceChildren(...questions.map(renderQuestion));
    addQuestionButton.disabled = questions.length >= MAX_QUESTIONS;
  }

  function showError(message) {
    formError.textContent = message;
    formError.hidden = false;
    formError.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function clearError() {
    formError.textContent = "";
    formError.hidden = true;
  }

  function uniqueNonEmpty(values) {
    const normalized = values.map((value) => value.trim().toLocaleLowerCase("fr"));
    return normalized.every(Boolean) && new Set(normalized).size === normalized.length;
  }

  function buildPayload() {
    const target = targetInput.value.trim();
    if (target.length < 3) throw new Error("Indiquez un domaine ou une URL valide.");

    const payloadQuestions = questions.map((question, index) => {
      const instructions = question.instructions.trim();
      if (instructions.length < 3) {
        throw new Error(`Complétez la question ${index + 1}.`);
      }
      if (question.type === "choice") {
        const options = question.options.map((option) => ({
          value: option.value.trim(),
          description: option.description.trim(),
        }));
        if (!uniqueNonEmpty(options.map((option) => option.value))) {
          throw new Error(`Les valeurs de la question ${index + 1} doivent être remplies et uniques.`);
        }
        if (options.some((option) => !option.description)) {
          throw new Error(`Décrivez toutes les options de la question ${index + 1}.`);
        }
        return { type: "choice", instructions, options };
      }
      if (question.type === "score") {
        const levels = question.levels.map((level) => level.trim());
        if (!uniqueNonEmpty(levels)) {
          throw new Error(`Les niveaux de la question ${index + 1} doivent être remplis et uniques.`);
        }
        return { type: "score", instructions, levels };
      }
      return { type: "noul", instructions };
    });

    return { target, questions: payloadQuestions };
  }

  function displayValue(value) {
    if (value === true) return "Oui";
    if (value === false) return "Non";
    if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
    return String(value);
  }

  function percent(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) return null;
    const normalized = value <= 1 ? value * 100 : value;
    return `${Math.round(normalized)} %`;
  }

  function stat(label, value) {
    const node = el("div", "summary-stat");
    node.append(el("span", "", label), el("strong", "", value));
    return node;
  }

  function renderResults(result) {
    const usage = result.usage || {};
    summaryRoot.replaceChildren(
      stat("Domaine", result.domain || "—"),
      stat("Pages visitées", String(result.pages_visited ?? 0)),
      stat("Entrée Jev", `${usage.input_tokens ?? 0} tokens`),
      stat("Sortie Jev", `${usage.output_tokens ?? 0} tokens`),
    );

    const answerEntries = Object.entries(result.answers || {});
    const answerNodes = answerEntries.map(([key, answer], index) => {
      const card = el("article", "answer-card");
      card.append(el("p", "answer-number", key.replace("question_", "Q")));
      card.append(el("p", "answer-question", questions[index]?.instructions || `Question ${index + 1}`));
      card.append(el("p", "answer-value", displayValue(answer.value)));
      const confidence = percent(answer.confidence);
      card.append(
        el(
          "p",
          "answer-meta",
          confidence ? `${answer.type} · confiance ${confidence}` : answer.type,
        ),
      );

      if (answer.probabilities && typeof answer.probabilities === "object") {
        const probabilityList = el("div", "probabilities");
        Object.entries(answer.probabilities).forEach(([label, value]) => {
          const row = el("div", "probability-row");
          row.append(el("span", "", label), el("span", "", percent(value) || String(value)));
          probabilityList.append(row);
        });
        card.append(probabilityList);
      }
      return card;
    });
    answersRoot.replaceChildren(...answerNodes);

    const evidence = Array.isArray(result.evidence) ? result.evidence : [];
    evidenceCount.textContent = `${evidence.length} page${evidence.length > 1 ? "s" : ""}`;
    if (!evidence.length) {
      evidenceRoot.replaceChildren(el("p", "empty-state", "Aucune page de preuve n’a été retournée."));
    } else {
      const evidenceNodes = evidence.map((item) => {
        const node = el("article", "evidence-item");
        const source = el("div", "evidence-source");
        const link = el("a", "", item.title || item.url || "Page consultée");
        try {
          const url = new URL(item.url);
          if (["http:", "https:"].includes(url.protocol)) {
            link.href = url.href;
            link.target = "_blank";
            link.rel = "noopener noreferrer";
          }
        } catch (_) {
          // Leave malformed upstream URLs inert.
        }
        source.append(link, el("div", "evidence-url", item.url || ""));
        source.append(el("div", "evidence-meta", `Transport : ${item.transport || "inconnu"}`));

        const excerpt = el("div", "");
        excerpt.append(el("p", "evidence-excerpt", item.excerpt || "Aucun extrait disponible."));
        if (item.truncated) {
          excerpt.append(el("p", "evidence-warning", "Extrait tronqué par la limite de sécurité."));
        }
        node.append(source, excerpt);
        return node;
      });
      evidenceRoot.replaceChildren(...evidenceNodes);
    }

    loadingPanel.hidden = true;
    resultsPanel.hidden = false;
    resultsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  addQuestionButton.addEventListener("click", () => {
    if (questions.length >= MAX_QUESTIONS) return;
    questions.push(createQuestion());
    renderQuestions();
    const lastInput = questionsRoot.querySelector(".question-card:last-child input");
    lastInput?.focus();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();

    let payload;
    try {
      payload = buildPayload();
    } catch (error) {
      showError(error.message);
      return;
    }

    submitButton.disabled = true;
    submitButton.querySelector(".button-label").textContent = "Analyse en cours…";
    resultsPanel.hidden = true;
    loadingPanel.hidden = false;
    loadingPanel.scrollIntoView({ behavior: "smooth", block: "center" });

    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.error || "Le service n’a pas pu terminer l’analyse.");
      }
      renderResults(data);
    } catch (error) {
      loadingPanel.hidden = true;
      showError(error.message || "Une erreur réseau est survenue.");
    } finally {
      submitButton.disabled = false;
      submitButton.querySelector(".button-label").textContent = "Analyser le site";
    }
  });

  newAnalysisButton.addEventListener("click", () => {
    document.querySelector("#analysis-title").scrollIntoView({ behavior: "smooth", block: "start" });
    targetInput.focus();
  });

  questions.push(createQuestion());
  renderQuestions();
})();
