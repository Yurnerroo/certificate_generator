const EN_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
];

const form = document.getElementById("cert-form");
const monthSelect = document.getElementById("month");
const yearInput = document.getElementById("year");
const datePreview = document.getElementById("date-preview");
const outputFolderInput = document.getElementById("output_folder");
const browseBtn = document.getElementById("browse-btn");
const generateBtn = document.getElementById("generate-btn");
const resultPanel = document.getElementById("result-panel");
const recipientsList = document.getElementById("recipients-list");
const addRecipientBtn = document.getElementById("add-recipient-btn");

let recipientRowCounter = 0;

function addRecipientRow(nameUk = "", nameEn = "") {
    recipientRowCounter += 1;
    const rowId = `recipient-${recipientRowCounter}`;
    const row = document.createElement("div");
    row.className = "recipient-row";
    row.dataset.rowId = rowId;
    row.innerHTML = `
        <input type="text" class="recipient-name-uk" placeholder="Коваль Марія" value="${escapeHtmlAttr(nameUk)}" required>
        <input type="text" class="recipient-name-en" placeholder="Залиште порожнім для автотранслітерації" value="${escapeHtmlAttr(nameEn)}">
        <button type="button" class="btn-remove-recipient" title="Видалити отримувача">&times;</button>
    `;
    recipientsList.appendChild(row);
    row.querySelector(".btn-remove-recipient").addEventListener("click", () => {
        if (recipientsList.children.length > 1) {
            row.remove();
        } else {
            row.querySelector(".recipient-name-uk").value = "";
            row.querySelector(".recipient-name-en").value = "";
        }
    });
}

function escapeHtmlAttr(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML.replace(/"/g, "&quot;");
}

function collectRecipients() {
    return Array.from(recipientsList.querySelectorAll(".recipient-row")).map((row) => ({
        name_uk: row.querySelector(".recipient-name-uk").value.trim(),
        name_en: row.querySelector(".recipient-name-en").value.trim(),
    }));
}

addRecipientBtn.addEventListener("click", () => addRecipientRow());
addRecipientRow();


function updateDatePreview() {
    const monthIdx = parseInt(monthSelect.value, 10) - 1;
    const monthLabel = monthSelect.options[monthSelect.selectedIndex]?.text || "";
    const year = yearInput.value || "";
    const enMonth = EN_MONTHS[monthIdx] || "";
    datePreview.textContent = year
        ? `Буде показано: "${monthLabel}, ${year}" / "${enMonth}, ${year}"`
        : "";
}

monthSelect.addEventListener("change", updateDatePreview);
yearInput.addEventListener("input", updateDatePreview);
updateDatePreview();

browseBtn.addEventListener("click", async () => {
    browseBtn.disabled = true;
    browseBtn.textContent = "Відкриваю...";
    try {
        const resp = await fetch("/api/browse-folder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ current_path: outputFolderInput.value }),
        });
        const data = await resp.json();
        if (data.error) {
            alert(data.error);
        } else if (data.path) {
            outputFolderInput.value = data.path;
        }
    } catch (err) {
        alert("Не вдалося відкрити діалог вибору папки: " + err);
    } finally {
        browseBtn.disabled = false;
        browseBtn.textContent = "Огляд...";
    }
});

function renderResult(data, isError) {
    resultPanel.classList.remove("hidden", "success", "error");
    resultPanel.classList.add(isError ? "error" : "success");

    if (isError) {
        resultPanel.innerHTML = `<h3>Помилка</h3><p>${escapeHtml(data.error || "Невідома помилка")}</p>`;
        return;
    }

    let html = `<h3>Готово! Згенеровано сертифікатів: ${data.files.length}</h3>`;
    html += `<p>Папка: <code>${escapeHtml(data.output_folder)}</code></p>`;
    if (data.files.length) {
        html += `<ul class="files-list">${data.files.map((f) => `<li>${escapeHtml(f)}</li>`).join("")}</ul>`;
    }
    if (data.warnings && data.warnings.length) {
        html += `<div class="warnings"><strong>Попередження:</strong><ul>${data.warnings
            .map((w) => `<li>${escapeHtml(w)}</li>`)
            .join("")}</ul></div>`;
    }
    html += `<div class="actions-row"><button type="button" class="btn-secondary" id="open-folder-btn">Відкрити папку</button></div>`;
    resultPanel.innerHTML = html;

    document.getElementById("open-folder-btn").addEventListener("click", async () => {
        try {
            const resp = await fetch("/api/open-folder", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ path: data.output_folder }),
            });
            const result = await resp.json();
            if (!result.success) {
                alert(result.error || "Не вдалося відкрити папку.");
            }
        } catch (err) {
            alert("Не вдалося відкрити папку: " + err);
        }
    });
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    generateBtn.disabled = true;
    generateBtn.textContent = "Генерую...";
    resultPanel.classList.add("hidden");

    const payload = {
        recipients: collectRecipients(),
        title_uk: document.getElementById("title_uk").value,
        title_en: document.getElementById("title_en").value,
        location_uk: document.getElementById("location_uk").value,
        location_en: document.getElementById("location_en").value,
        month: parseInt(monthSelect.value, 10),
        year: parseInt(yearInput.value, 10),
        output_folder: outputFolderInput.value,
    };

    try {
        const resp = await fetch("/api/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();
        renderResult(data, !resp.ok || !data.success);
    } catch (err) {
        renderResult({ error: String(err) }, true);
    } finally {
        generateBtn.disabled = false;
        generateBtn.textContent = "Згенерувати сертифікати";
    }
});
