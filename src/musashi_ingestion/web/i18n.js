(() => {
  "use strict";
  const storageKey = "musashi.language";
  let language = "en";
  try { if (localStorage.getItem(storageKey) === "th") language = "th"; } catch { /* Storage may be disabled. */ }
  const t = value => language === "th" ? window.MusashiThai[value] ?? value : value;
  function pattern(value) {
    const indices = [];
    const normalized = value.replace(/\{(\d+)\}/g, (_, index) => {
      if (!indices.includes(index)) indices.push(index);
      return `{${indices.indexOf(index)}}`;
    });
    return t(normalized).replace(/\{(\d+)\}/g, (_, index) => `{${indices[Number(index)]}}`);
  }
  const messages = new Map();
  function retranslate(value) {
    if (messages.has(value)) {
      const [source, values] = messages.get(value);
      return pattern(source).replace(/\{(\d+)\}/g, (_, index) => String(values[Number(index)]));
    }
    const english = Object.keys(window.MusashiThai).find(key => window.MusashiThai[key] === value) || value;
    return t(english);
  }
  const escapeAttribute = value => value.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const decode = value => value.replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#39;/g, "'");
  // Translate authored text only. Interpolated data is inserted after translation.
  function translateText(text) {
    const match = text.match(/^(\s*)(.*?)(\s*)$/s);
    return match ? match[1] + pattern(decode(match[2])) + match[3] : text;
  }
  function html(source) {
    const attributes = source.replace(/\b(aria-label|aria-valuetext|title|placeholder)="([^"]*)"/g, (_, attr, value) => `${attr}="${escapeAttribute(pattern(decode(value)))}"`);
    return attributes.split(/(<[^>]*>)/g).map(part => part.startsWith("<") ? part : translateText(part)).join("");
  }
  function msg(strings, ...values) {
    const source = strings.reduce((text, part, index) => text + (index ? `{${index - 1}}` : "") + part, "");
    const translated = source.includes("<") ? html(source) : pattern(source);
    const result = translated.replace(/\{(\d+)\}/g, (_, index) => String(values[Number(index)]));
    if (!source.includes("<") && Object.hasOwn(window.MusashiThai, source)) {
      messages.set(result, [source, values]);
      if (messages.size > 128) messages.delete(messages.keys().next().value);
    }
    return result;
  }
  const originalText = new WeakMap(), originalAttributes = new WeakMap();
  function translateShell() {
    const root = document.body;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (node.parentElement.closest("#page-content, #edit-fields, #notice, #login-error, #edit-error, #confirm-title, #confirm-copy, #connection-label, #last-updated, #crumb-page, script, style, [data-language-control]")) continue;
      if (!originalText.has(node)) originalText.set(node, node.nodeValue);
      node.nodeValue = translateText(originalText.get(node));
    }
    root.querySelectorAll("[aria-label], [title], [placeholder]").forEach(node => {
      if (node.closest("#page-content, #edit-fields, [data-language-control]")) return;
      if (!originalAttributes.has(node)) originalAttributes.set(node, Object.fromEntries(["aria-label", "title", "placeholder"].filter(attr => node.hasAttribute(attr)).map(attr => [attr, node.getAttribute(attr)])));
      Object.entries(originalAttributes.get(node)).forEach(([attr,value]) => node.setAttribute(attr,t(value)));
    });
    document.documentElement.lang = language;
    document.querySelectorAll("[data-language-select]").forEach(select => { select.value = language; select.setAttribute("aria-label", t("Language")); });
  }
  function setLanguage(value) {
    if (!["en", "th"].includes(value) || value === language) return;
    language = value;
    try { localStorage.setItem(storageKey, language); } catch { /* Selection still works for this session. */ }
    translateShell();
    window.dispatchEvent(new Event("musashi:languagechange"));
  }
  window.MusashiI18n = Object.freeze({t, html, msg, retranslate, setLanguage, translateShell, get language() { return language; }, get locale() { return language === "th" ? "th-TH" : "en-US"; }});
  document.addEventListener("DOMContentLoaded", () => {
    translateShell();
    document.querySelectorAll("[data-language-select]").forEach(select => select.addEventListener("change", () => setLanguage(select.value)));
  });
})();
