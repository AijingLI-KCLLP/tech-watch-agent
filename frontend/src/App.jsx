import { useEffect, useRef, useState } from "react";

const DASHBOARD_ARTICLE_LIMIT = 10;
const LIBRARY_PAGE_SIZE = 20;
const CATEGORIES = [
  "inbox",
  "ai_automation",
  "tech_code",
  "product_business",
  "science_research",
  "design_creativity",
  "culture_society",
  "learning_life",
];
const DISCOVERY_CATEGORIES = CATEGORIES.filter((category) => category !== "inbox");

async function request(path, options = {}) {
  const response = await fetch(path, options);
  if (response.ok) return response.status === 204 ? null : response.json();

  const payload = await response.json().catch(() => ({}));
  throw new Error(payload.detail || "The request could not be completed.");
}

function errorMessage(error) {
  return error instanceof Error ? error.message : "Something went wrong.";
}

function formatArticleDate(dateValue) {
  const date = new Date(dateValue);
  return Number.isNaN(date.valueOf()) ? "unknown date" : date.toLocaleDateString();
}

function formatCategory(category) {
  return (category || "inbox").replaceAll("_", " ");
}

function MessageContent({ content, onEditArticle, role }) {
  if (role !== "assistant") return content;
  const references = /(\[source:\s*([a-z0-9-]+)\]|\[([a-f0-9]{16,})\]|【([a-f0-9]{16,})】)/gi;
  const parts = [];
  let cursor = 0;
  let match;
  while ((match = references.exec(content)) !== null) {
    if (match.index > cursor) parts.push(content.slice(cursor, match.index));
    const articleId = match[2] || match[3] || match[4];
    parts.push(<button className="source-reference" key={`${articleId}-${match.index}`} onClick={() => onEditArticle(articleId)} type="button">{match[1]}</button>);
    cursor = match.index + match[0].length;
  }
  if (cursor < content.length) parts.push(content.slice(cursor));
  return parts.length ? parts : content;
}

function ArticleList({ articles, deletingArticleId, error, onDelete, onEdit }) {
  if (error) {
    return <p className="empty-state">Could not load articles: {error}</p>;
  }
  if (articles === null) {
    return <p className="empty-state">Loading library...</p>;
  }
  if (articles.length === 0) {
    return <p className="empty-state">Your library is empty. Start by watching a topic.</p>;
  }

  return articles.map((article) => (
    <article className="article-row" key={article.id}>
      <div className="article-heading">
        <div className="article-title-line">
          <span className="category-badge" data-category={article.category || "inbox"}>
            {formatCategory(article.category)}
          </span>
          {article.url || article.raw_file_url ? (
            <a className="article-title" href={article.url || article.raw_file_url} rel="noreferrer" target="_blank">
              {article.title}
            </a>
          ) : (
            <span className="article-title">{article.title}</span>
          )}
        </div>
        {article.tags?.length > 0 && (
          <ul aria-label={`Tags for ${article.title}`} className="tag-list">
            {article.tags.map((tag) => <li key={tag}>{tag}</li>)}
          </ul>
        )}
      </div>
      <div className="article-actions">
        <p className="article-meta">
          {article.source_name || "unknown source"} / {formatArticleDate(article.fetched_at)} / {article.n_tags} tags
        </p>
        {article.raw_file_url && (
          <a className="raw-file-link" href={article.raw_file_url} rel="noreferrer" target="_blank">Raw image</a>
        )}
        <button className="edit-button" onClick={() => onEdit(article.id)} type="button">Manual edit</button>
        <button
          className="delete-button"
          disabled={deletingArticleId === article.id}
          onClick={() => onDelete(article)}
          type="button"
        >
          {deletingArticleId === article.id ? "Deleting..." : "Delete"}
        </button>
      </div>
    </article>
  ));
}

function sourceVerificationLabel(status) {
  return (status || "not recorded").replaceAll("_", " ");
}

function ArticleEditor({ articleId, onClose, onSaved }) {
  const [article, setArticle] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(null);

  useEffect(() => {
    let active = true;
    setArticle(null);
    setForm(null);
    setError("");
    request(`/articles/${articleId}`)
      .then((result) => {
        if (!active) return;
        setArticle(result);
        setForm({
          title: result.title,
          content: result.content,
          summary: result.summary || "",
          category: result.category,
          tags: result.tags.join(", "),
        });
      })
      .catch((loadError) => active && setError(errorMessage(loadError)));
    return () => { active = false; };
  }, [articleId]);

  function setField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!form) return;

    setSaving(true);
    setError("");
    try {
      const updated = await request(`/articles/${articleId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: form.title.trim(),
          content: form.content.trim(),
          summary: form.summary.trim() || null,
          category: form.category,
          tags: form.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
        }),
      });
      setArticle(updated);
      await onSaved();
      onClose();
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="editor-backdrop" onMouseDown={onClose}>
      <section aria-labelledby="editor-title" aria-modal="true" className="article-editor" onMouseDown={(event) => event.stopPropagation()} role="dialog">
        <div className="editor-heading">
          <div>
            <p className="section-number">ARTICLE REVIEW</p>
            <h2 id="editor-title">Manual edit</h2>
          </div>
          <button aria-label="Close manual edit" className="close-button" onClick={onClose} type="button">Close</button>
        </div>
        {error && <p className="editor-error" role="alert">{error}</p>}
        {!article || !form ? (
          <p className="empty-state">Loading article…</p>
        ) : (
          <form className="editor-form" onSubmit={handleSubmit}>
            <label htmlFor="edit-title">Title</label>
            <input id="edit-title" maxLength="500" onChange={(event) => setField("title", event.target.value)} required value={form.title} />

            <label htmlFor="edit-content">Normalized content</label>
            <textarea id="edit-content" maxLength="100000" minLength="1" onChange={(event) => setField("content", event.target.value)} required rows="14" value={form.content} />

            <div className="editor-fields">
              <div>
                <label htmlFor="edit-category">Category</label>
                <select id="edit-category" onChange={(event) => setField("category", event.target.value)} value={form.category}>
                  {CATEGORIES.map((category) => <option key={category} value={category}>{formatCategory(category)}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="edit-tags">Tags</label>
                <input id="edit-tags" onChange={(event) => setField("tags", event.target.value)} placeholder="ai, agents, research" value={form.tags} />
              </div>
            </div>

            <label htmlFor="edit-summary">Summary</label>
            <textarea id="edit-summary" maxLength="5000" onChange={(event) => setField("summary", event.target.value)} rows="3" value={form.summary} />

            <section aria-labelledby="verification-title" className="provenance-panel">
              <h3 id="verification-title">Source verification</h3>
              {article.input_assets.length === 0 ? (
                <p>No provenance record was retained for this article.</p>
              ) : article.input_assets.map((asset) => (
                <div className="provenance-record" key={asset.id}>
                  <p><strong>{sourceVerificationLabel(asset.source_verification_status)}</strong>{asset.source_verification_confidence !== null && ` · ${Math.round(asset.source_verification_confidence * 100)}% confidence`}</p>
                  {asset.source_verification_reason && <p>{asset.source_verification_reason}</p>}
                  {asset.provided_source_url && <a href={asset.provided_source_url} rel="noreferrer" target="_blank">Provided source URL</a>}
                  {asset.provided_source_reference && <p>Original source: {asset.provided_source_reference}</p>}
                </div>
              ))}
            </section>

            <section aria-labelledby="raw-input-title" className="provenance-panel">
              <h3 id="raw-input-title">Original raw input</h3>
              {article.input_assets.length === 0 ? (
                <p>No original input was retained for this article.</p>
              ) : article.input_assets.map((asset) => (
                <div className="provenance-record" key={asset.id}>
                  <p>{asset.input_filename || `${asset.original_type} input`}</p>
                  {asset.raw_text ? <pre>{asset.raw_text}</pre> : <p>Raw text is unavailable for this uploaded file.</p>}
                  {asset.storage_path && <a href={`/input-assets/${asset.id}/file`} rel="noreferrer" target="_blank">Open original file</a>}
                </div>
              ))}
            </section>

            <div className="editor-actions">
              <button className="close-button" onClick={onClose} type="button">Cancel</button>
              <button disabled={saving} type="submit">{saving ? "Saving…" : "Save article"}</button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}

function pageFromHash() {
  if (window.location.hash === "#/articles") return "articles";
  if (window.location.hash === "#/drafts") return "drafts";
  if (window.location.hash === "#/conversations") return "conversations";
  return "dashboard";
}

function clipboardFile(event) {
  const file = event.clipboardData.files[0]
    || [...event.clipboardData.items]
      .find((item) => item.kind === "file")
      ?.getAsFile();
  if (!file) return null;
  if (file.name) return file;

  const extension = file.type.split("/")[1] || "bin";
  return new File([file], `pasted-file.${extension}`, { type: file.type });
}

const DRAFT_SUGGESTIONS = {
  language: ["English", "French", "Chinese (Simplified)"],
  audience: ["Engineering team", "Product and business leaders", "Potential clients", "Founders and operators", "Technical peers", "General audience"],
  objective: ["Share a practical insight", "Teach a concrete method", "Explain a strategic decision", "Build credibility with clients", "Start a professional discussion", "Challenge a common assumption", "Share a lesson learned", "Get feedback on an idea", "Attract collaborators or candidates", "Turn research into an actionable takeaway", "Document a team practice", "Announce a new direction"],
  tone: ["Clear and pragmatic", "Confident and opinionated", "Warm and conversational", "Analytical and nuanced", "Direct and concise", "Educational and structured"],
};

function SuggestedInput({ field, label, onChange, value }) {
  const listId = `draft-${field}-suggestions`;
  return (
    <div>
      <label htmlFor={`draft-${field}`}>{label}</label>
      <input id={`draft-${field}`} list={listId} onChange={(event) => onChange(field, event.target.value)} placeholder="Choose below or type your own" required value={value} />
      <datalist id={listId}>
        {DRAFT_SUGGESTIONS[field].map((suggestion) => <option key={suggestion} value={suggestion} />)}
      </datalist>
      <div aria-label={`${label} suggestions`} className="suggestion-options">
        {DRAFT_SUGGESTIONS[field].map((suggestion) => <button className={value === suggestion ? "suggestion-option is-selected" : "suggestion-option"} key={suggestion} onClick={() => onChange(field, suggestion)} type="button">{suggestion}</button>)}
      </div>
    </div>
  );
}

function LanguageSelect({ onChange, value }) {
  return <div>
    <label htmlFor="draft-language">Language</label>
    <select id="draft-language" onChange={(event) => onChange("language", event.target.value)} value={value}>
      {DRAFT_SUGGESTIONS.language.map((language) => <option key={language} value={language}>{language}</option>)}
    </select>
  </div>;
}

function DraftComposer({ onCreated }) {
  const [form, setForm] = useState({
    intent: "",
    format: "post",
    platform: "LinkedIn",
    language: "English",
    audience: "Engineering team",
    objective: "Share a practical insight",
    tone: "Clear and pragmatic",
    personal_angle: "",
    enrich_with_web: true,
  });
  const [error, setError] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);

  function setField(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setIsGenerating(true);
    try {
      const draft = await request("/drafts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, intent: form.intent.trim(), personal_angle: form.personal_angle.trim() }),
      });
      onCreated(draft.id);
    } catch (generateError) {
      setError(errorMessage(generateError));
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <section className="draft-composer" aria-labelledby="draft-composer-title">
      <div className="section-heading">
        <div>
          <p className="section-number">04 / DRAFT</p>
          <h2 id="draft-composer-title">Turn an idea into a draft.</h2>
        </div>
      </div>
      <p className="draft-copy">Describe what you want to share. The cabinet finds relevant library sources, can enrich them from the web, then produces a local draft for human review.</p>
      <form className="draft-form" onSubmit={handleSubmit}>
        <label htmlFor="draft-intent">What do you want to share?</label>
        <textarea id="draft-intent" maxLength="2000" minLength="1" onChange={(event) => setField("intent", event.target.value)} placeholder="For example: I want to share a practical view on how small teams can use AI agents without adding unnecessary complexity." required rows="3" value={form.intent} />
        <div className="editor-fields">
          <div>
            <label htmlFor="draft-format">Format</label>
            <select id="draft-format" onChange={(event) => setField("format", event.target.value)} value={form.format}>
              <option value="post">Post</option>
              <option value="note">Note</option>
            </select>
          </div>
          <div>
            <label htmlFor="draft-platform">Platform</label>
            <select id="draft-platform" onChange={(event) => setField("platform", event.target.value)} value={form.platform}>
              <option value="LinkedIn">LinkedIn</option>
              <option value="X / Twitter">X / Twitter</option>
              <option value="RedNote">RedNote</option>
              <option value="none">No platform / neutral</option>
            </select>
          </div>
          <LanguageSelect onChange={setField} value={form.language} />
          <SuggestedInput field="audience" label="Audience" onChange={setField} value={form.audience} />
          <SuggestedInput field="objective" label="Objective" onChange={setField} value={form.objective} />
          <SuggestedInput field="tone" label="Tone" onChange={setField} value={form.tone} />
        </div>
        <label htmlFor="draft-angle">Your personal angle</label>
        <textarea id="draft-angle" maxLength="2000" minLength="1" onChange={(event) => setField("personal_angle", event.target.value)} placeholder="What do you personally want to add, question, or challenge?" required rows="3" value={form.personal_angle} />
        <label className="web-enrichment-option" htmlFor="draft-web-enrichment">
          <input checked={form.enrich_with_web} id="draft-web-enrichment" onChange={(event) => setField("enrich_with_web", event.target.checked)} type="checkbox" />
          Enrich with recent web sources before drafting
        </label>
        {error && <p className="editor-error" role="alert">Could not generate draft: {error}</p>}
        <div className="editor-actions">
          <button disabled={isGenerating} type="submit">{isGenerating ? "Finding sources and drafting…" : "Find sources and generate draft"}</button>
        </div>
      </form>
    </section>
  );
}

function DraftEditor({ draftId, onClose, onSaved }) {
  const [draft, setDraft] = useState(null);
  const [form, setForm] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  useEffect(() => {
    let active = true;
    setDraft(null); setForm(null); setError("");
    request(`/drafts/${draftId}`).then((result) => {
      if (!active) return;
      setDraft(result);
      setForm({ title: result.title, intent: result.intent, platform: result.platform, content: result.content, language: result.language, audience: result.audience, objective: result.objective, tone: result.tone, personal_angle: result.personal_angle, status: result.status });
    }).catch((loadError) => active && setError(errorMessage(loadError)));
    return () => { active = false; };
  }, [draftId]);

  function setField(field, value) { setForm((current) => ({ ...current, [field]: value })); }

  async function save(event) {
    event.preventDefault();
    if (!form) return;
    setSaving(true); setError("");
    try {
      const updated = await request(`/drafts/${draftId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(Object.entries(form).map(([key, value]) => [key, typeof value === "string" ? value.trim() : value]))) });
      setDraft(updated);
      await onSaved();
    } catch (saveError) { setError(errorMessage(saveError)); } finally { setSaving(false); }
  }

  async function regenerate() {
    if (!window.confirm("Regenerate this draft from its selected sources? Your current manual edits will be replaced.")) return;
    setRegenerating(true); setError("");
    try {
      const updated = await request(`/drafts/${draftId}/regenerate`, { method: "POST" });
      setDraft(updated);
      setForm({ title: updated.title, intent: updated.intent, platform: updated.platform, content: updated.content, language: updated.language, audience: updated.audience, objective: updated.objective, tone: updated.tone, personal_angle: updated.personal_angle, status: updated.status });
      await onSaved();
    } catch (regenerateError) { setError(errorMessage(regenerateError)); } finally { setRegenerating(false); }
  }

  return <div className="editor-backdrop" onMouseDown={onClose}>
    <section aria-labelledby="draft-editor-title" aria-modal="true" className="article-editor draft-editor" onMouseDown={(event) => event.stopPropagation()} role="dialog">
      <div className="editor-heading"><div><p className="section-number">UNPUBLISHED DRAFT</p><h2 id="draft-editor-title">Manual edit</h2></div><button className="close-button" onClick={onClose} type="button">Close</button></div>
      {error && <p className="editor-error" role="alert">{error}</p>}
      {!draft || !form ? <p className="empty-state">Loading draft…</p> : <form className="editor-form" onSubmit={save}>
        <label htmlFor="draft-edit-title">Title</label><input id="draft-edit-title" maxLength="500" onChange={(event) => setField("title", event.target.value)} required value={form.title} />
        <label htmlFor="draft-edit-intent">Sharing intent</label><textarea id="draft-edit-intent" maxLength="2000" onChange={(event) => setField("intent", event.target.value)} required rows="3" value={form.intent} />
        <div><label htmlFor="draft-edit-platform">Platform</label><select id="draft-edit-platform" onChange={(event) => setField("platform", event.target.value)} value={form.platform}><option value="LinkedIn">LinkedIn</option><option value="X / Twitter">X / Twitter</option><option value="RedNote">RedNote</option><option value="none">No platform / neutral</option></select></div>
        <div className="editor-fields"><LanguageSelect onChange={setField} value={form.language} /><SuggestedInput field="audience" label="Audience" onChange={setField} value={form.audience} /><SuggestedInput field="objective" label="Objective" onChange={setField} value={form.objective} /><SuggestedInput field="tone" label="Tone" onChange={setField} value={form.tone} /></div>
        <label htmlFor="draft-edit-angle">Your personal angle</label><textarea id="draft-edit-angle" maxLength="2000" onChange={(event) => setField("personal_angle", event.target.value)} required rows="3" value={form.personal_angle} />
        <label htmlFor="draft-edit-content">Draft content</label><textarea id="draft-edit-content" maxLength="100000" minLength="1" onChange={(event) => setField("content", event.target.value)} required rows="18" value={form.content} />
        <div className="editor-fields"><div><label htmlFor="draft-status">Review status</label><select id="draft-status" onChange={(event) => setField("status", event.target.value)} value={form.status}><option value="draft">Draft</option><option value="reviewed">Reviewed</option></select></div></div>
        <section className="provenance-panel"><h3>Selected sources</h3>{draft.articles.map((article) => <p key={article.id}>{article.position + 1}. {article.url ? <a href={article.url} rel="noreferrer" target="_blank">{article.title}</a> : article.title}</p>)}</section>
        <div className="editor-actions"><button className="close-button" disabled={regenerating || saving} onClick={regenerate} type="button">{regenerating ? "Regenerating…" : "Regenerate"}</button><button disabled={saving || regenerating} type="submit">{saving ? "Saving…" : "Save draft"}</button></div>
      </form>}
    </section>
  </div>;
}

function DraftsPage() {
  const [drafts, setDrafts] = useState(null);
  const [error, setError] = useState("");
  const [editingDraftId, setEditingDraftId] = useState("");
  async function loadDrafts() {
    setError("");
    try { const result = await request("/drafts"); setDrafts(result.items); } catch (loadError) { setError(errorMessage(loadError)); }
  }
  useEffect(() => { loadDrafts(); }, []);
  return <section className="library-panel" aria-labelledby="drafts-title">
    <div className="section-heading"><div><p className="section-number">DRAFTS</p><h1 id="drafts-title">Unpublished drafts</h1></div><a className="library-link" href="#/">Dashboard</a></div>
    <p className="draft-copy">Drafts are saved locally. Review, edit, and publish them yourself when they are ready.</p>
    {error && <p className="empty-state">Could not load drafts: {error}</p>}
    {drafts === null && !error && <p className="empty-state">Loading drafts…</p>}
    {drafts?.length === 0 && <p className="empty-state">No drafts yet. Describe what you want to share and generate one.</p>}
    <div className="article-list">{drafts?.map((draft) => <article className="article-row" key={draft.id}><div className="article-heading"><div className="article-title-line"><span className="category-badge">{draft.format}</span><button className="draft-title" onClick={() => setEditingDraftId(draft.id)} type="button">{draft.title}</button></div><p className="article-meta draft-meta">{draft.platform} / {draft.language} / {draft.audience} / {draft.article_count} sources</p></div><div className="article-actions"><p className="article-meta">{draft.status} / updated {formatArticleDate(draft.updated_at)}</p><button className="edit-button" onClick={() => setEditingDraftId(draft.id)} type="button">Edit draft</button></div></article>)}</div>
    {editingDraftId && <DraftEditor draftId={editingDraftId} onClose={() => setEditingDraftId("")} onSaved={loadDrafts} />}
  </section>;
}

function ConversationHistoryPage({ onEditArticle, onOpen }) {
  const [conversations, setConversations] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    request("/conversations")
      .then(setConversations)
      .catch((loadError) => setError(errorMessage(loadError)));
  }, []);

  async function inspectConversation(id) {
    setError("");
    try { setSelected(await request(`/conversations/${id}`)); } catch (loadError) { setError(errorMessage(loadError)); }
  }

  return <section className="conversation-history-page" aria-labelledby="history-title">
    <div className="section-heading"><div><p className="section-number">HISTORY</p><h1 id="history-title">Ask conversations</h1></div><a className="library-link" href="#/">Dashboard</a></div>
    <p className="draft-copy">Your RAG discussions are saved locally. Open one to continue asking in the same context.</p>
    {error && <p className="empty-state">Could not load conversations: {error}</p>}
    {conversations === null && !error && <p className="empty-state">Loading conversations…</p>}
    {conversations?.length === 0 && <p className="empty-state">No conversations yet. Ask the cabinet a question to start one.</p>}
    <div className="conversation-history-grid">
      <div className="conversation-list">{conversations?.map((conversation) => <button className={selected?.id === conversation.id ? "conversation-card is-selected" : "conversation-card"} key={conversation.id} onClick={() => inspectConversation(conversation.id)} type="button"><strong>{conversation.title}</strong><span>{conversation.message_count} messages · {formatArticleDate(conversation.updated_at)}</span></button>)}</div>
      <section className="conversation-preview" aria-live="polite">
        {!selected ? <p>Select a conversation to read it.</p> : <><div className="editor-heading"><h2>{selected.title}</h2><button onClick={() => onOpen(selected)} type="button">Continue</button></div><div className="chat-history">{selected.messages.map((message) => <div className={`chat-message ${message.role}`} key={message.id}><span>{message.role === "user" ? "You" : "Cabinet"}</span><p><MessageContent content={message.content} onEditArticle={onEditArticle} role={message.role} /></p></div>)}</div></>}
      </section>
    </div>
  </section>;
}

function FilePreview({ file, imagePreviewUrl, onClear }) {
  if (!file) return null;

  const extension = file.name.split(".").pop()?.toUpperCase() || "FILE";
  return (
    <div className="file-preview">
      {imagePreviewUrl ? (
        <img alt={`Preview of ${file.name}`} src={imagePreviewUrl} />
      ) : (
        <div aria-hidden="true" className="file-preview-type">{extension}</div>
      )}
      <div>
        <p>{file.name}</p>
        <span>{file.type || "Unknown type"}</span>
      </div>
      <button aria-label={`Remove ${file.name}`} onClick={onClear} type="button">Remove</button>
    </div>
  );
}

function TopicDiscovery({ categories, isLoading, onCategoryChange, onCollect, onRefresh, status, topics }) {
  return (
    <section aria-labelledby="discovery-title" className="discovery-panel">
      <div className="discovery-heading">
        <div>
          <p className="section-number">01A / DISCOVER</p>
          <h2 id="discovery-title">What is hot right now?</h2>
        </div>
        <button disabled={isLoading || categories.length === 0} onClick={onRefresh} type="button">
          {isLoading ? "Refreshing…" : "Refresh topics"}
        </button>
      </div>
      <p className="discovery-copy">Recent news from the past week, limited to the trusted publishers configured for each category. Pick categories, then collect any headline as a new watch.</p>
      <fieldset className="discovery-categories">
        <legend className="sr-only">Categories for topic discovery</legend>
        {DISCOVERY_CATEGORIES.map((category) => (
          <label key={category}>
            <input checked={categories.includes(category)} onChange={() => onCategoryChange(category)} type="checkbox" />
            {formatCategory(category)}
          </label>
        ))}
      </fieldset>
      {status && <p aria-live="polite" className="status">{status}</p>}
      {!isLoading && topics.length > 0 && (
        <div className="discovery-list">
          {topics.map((suggestion) => (
            <article className="discovery-topic" key={`${suggestion.category}-${suggestion.source_url}`}>
              <span className="category-badge" data-category={suggestion.category}>{formatCategory(suggestion.category)}</span>
              <h3>{suggestion.topic}</h3>
              {suggestion.description && <p>{suggestion.description}</p>}
              <div>
                <button disabled={isLoading} onClick={() => onCollect(suggestion.topic)} type="button">Collect this topic</button>
                <a href={suggestion.source_url} rel="noreferrer" target="_blank">Read source</a>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function Pagination({ currentPage, total, onNext, onPrevious }) {
  const totalPages = Math.ceil(total / LIBRARY_PAGE_SIZE);
  if (totalPages < 2) return null;

  return (
    <nav aria-label="Article pages" className="pagination">
      <button disabled={currentPage === 0} onClick={onPrevious} type="button">Newer</button>
      <p className="count">PAGE {currentPage + 1} / {totalPages}</p>
      <button disabled={currentPage + 1 >= totalPages} onClick={onNext} type="button">Older</button>
    </nav>
  );
}

export default function App() {
  const [articles, setArticles] = useState(null);
  const [articleTotal, setArticleTotal] = useState(0);
  const [articleError, setArticleError] = useState("");
  const [page, setPage] = useState(pageFromHash);
  const [libraryPage, setLibraryPage] = useState(0);
  const [topic, setTopic] = useState("");
  const [watchStatus, setWatchStatus] = useState("");
  const [isWatching, setIsWatching] = useState(false);
  const [discoveryCategories, setDiscoveryCategories] = useState(["tech_code", "ai_automation"]);
  const [discoveryTopics, setDiscoveryTopics] = useState([]);
  const [discoveryStatus, setDiscoveryStatus] = useState("");
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [contentText, setContentText] = useState("");
  const [contentFile, setContentFile] = useState(null);
  const [imagePreviewUrl, setImagePreviewUrl] = useState("");
  const [contentTitle, setContentTitle] = useState("");
  const [contentSourceUrl, setContentSourceUrl] = useState("");
  const [urlContentType, setUrlContentType] = useState("article");
  const [contentUrl, setContentUrl] = useState("");
  const [podcastTranscript, setPodcastTranscript] = useState("");
  const [podcastTranscriptUrl, setPodcastTranscriptUrl] = useState("");
  const [contentStatus, setContentStatus] = useState("");
  const [isAddingContent, setIsAddingContent] = useState(false);
  const [isAddingUrl, setIsAddingUrl] = useState(false);
  const [deletingArticleId, setDeletingArticleId] = useState("");
  const [editingArticleId, setEditingArticleId] = useState("");
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState("");
  const [chatMessages, setChatMessages] = useState([]);
  const [isAsking, setIsAsking] = useState(false);
  const fileInputRef = useRef(null);

  const showAllArticles = page === "articles";
  const isDraftsPage = page === "drafts";
  const isConversationsPage = page === "conversations";

  const articleLimit = showAllArticles ? LIBRARY_PAGE_SIZE : DASHBOARD_ARTICLE_LIMIT;
  const articleOffset = showAllArticles ? libraryPage * LIBRARY_PAGE_SIZE : 0;

  async function loadArticles() {
    setArticleError("");
    setArticles(null);
    try {
      const result = await request(`/articles?limit=${articleLimit}&offset=${articleOffset}`);
      setArticles(result.items);
      setArticleTotal(result.total);
      return result;
    } catch (error) {
      setArticleError(errorMessage(error));
      return null;
    }
  }

  useEffect(() => {
    loadArticles();
  }, [articleLimit, articleOffset]);

  useEffect(() => {
    function handleHashChange() {
      setPage(pageFromHash());
      setLibraryPage(0);
    }

    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  useEffect(() => {
    if (!contentFile?.type.startsWith("image/")) {
      setImagePreviewUrl("");
      return undefined;
    }

    const previewUrl = URL.createObjectURL(contentFile);
    setImagePreviewUrl(previewUrl);
    return () => URL.revokeObjectURL(previewUrl);
  }, [contentFile]);

  async function collectTopic(rawTopic) {
    const normalizedTopic = rawTopic.trim();
    if (!normalizedTopic) return;

    setIsWatching(true);
    setWatchStatus("Searching, chunking, embedding, and storing...");
    try {
      const result = await request("/watch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic: normalizedTopic }),
      });
      setWatchStatus(`Saved ${result.article_count} articles and ${result.chunk_count} chunks.`);
      await loadArticles();
    } catch (error) {
      setWatchStatus(`Collection failed: ${errorMessage(error)}`);
    } finally {
      setIsWatching(false);
    }
  }

  async function handleWatch(event) {
    event.preventDefault();
    await collectTopic(topic);
  }

  async function loadDiscovery(categories = discoveryCategories) {
    if (categories.length === 0) {
      setDiscoveryTopics([]);
      setDiscoveryStatus("Choose at least one category to discover topics.");
      return;
    }
    const params = new URLSearchParams();
    categories.forEach((category) => params.append("categories", category));
    setIsDiscovering(true);
    setDiscoveryStatus("Finding this week’s technical signals…");
    try {
      const result = await request(`/discover/topics?${params}`);
      setDiscoveryTopics(result);
      setDiscoveryStatus(result.length ? "" : "No recent topics found. Try another category or refresh later.");
    } catch (error) {
      setDiscoveryTopics([]);
      setDiscoveryStatus(`Could not discover topics: ${errorMessage(error)}`);
    } finally {
      setIsDiscovering(false);
    }
  }

  function handleDiscoveryCategory(category) {
    setDiscoveryCategories((current) => (
      current.includes(category)
        ? current.filter((value) => value !== category)
        : [...current, category]
    ));
  }

  async function handleCollectDiscoveredTopic(topicToCollect) {
    setTopic(topicToCollect);
    await collectTopic(topicToCollect);
  }

  useEffect(() => {
    if (!showAllArticles && !isDraftsPage && !isConversationsPage) loadDiscovery();
  }, [showAllArticles, isDraftsPage, isConversationsPage]);

  async function handleAddContent(event) {
    event.preventDefault();
    const title = contentTitle.trim();
    const sourceReference = contentSourceUrl.trim();
    const providedSourceUrl = /^https?:\/\//i.test(sourceReference) ? sourceReference : "";

    setIsAddingContent(true);
    setContentStatus("Transcribing, normalizing, embedding, and storing...");
    try {
      let result;
      if (contentFile) {
        const formData = new FormData();
        formData.append("file", contentFile);
        if (title) formData.append("title", title);
        if (providedSourceUrl) formData.append("provided_source_url", providedSourceUrl);
        if (sourceReference) formData.append("provided_source_reference", sourceReference);
        result = await request("/content/file", { method: "POST", body: formData });
      } else {
        const text = contentText.trim();
        if (!text) {
          setContentStatus("Paste text to add it to the library.");
          return;
        }
        result = await request("/content/text", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text,
            ...(title && { title }),
            ...(providedSourceUrl && { provided_source_url: providedSourceUrl }),
            ...(sourceReference && { provided_source_reference: sourceReference }),
          }),
        });
      }
      setContentStatus(
        `Saved ${result.article.title} with ${result.chunk_count} chunks. Source: ${result.source_verification_status}.`,
      );
      setContentText("");
      setContentFile(null);
      setContentTitle("");
      setContentSourceUrl("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      await loadArticles();
    } catch (error) {
      setContentStatus(`Could not add content: ${errorMessage(error)}`);
    } finally {
      setIsAddingContent(false);
    }
  }

  function handleContentPaste(event) {
    const file = clipboardFile(event);
    if (!file) return;

    event.preventDefault();
    setContentFile(file);
    setContentStatus(`Pasted ${file.name}. Ready to add to the library.`);
  }

  function clearContentFile() {
    setContentFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleAddUrl() {
    const url = contentUrl.trim();
    if (!url) {
      setContentStatus(`Enter a ${urlContentType === "article" ? "URL" : urlContentType === "youtube" ? "YouTube video URL" : "podcast episode URL"} first.`);
      return;
    }
    const transcript = podcastTranscript.trim();
    const transcriptUrl = podcastTranscriptUrl.trim();
    if (urlContentType === "podcast" && transcript && transcriptUrl) {
      setContentStatus("For a podcast, provide transcript text or a transcript URL, not both.");
      return;
    }

    setIsAddingUrl(true);
    setContentStatus(
      urlContentType === "youtube"
        ? "Retrieving captions, embedding, and storing..."
        : urlContentType === "podcast"
          ? "Normalizing transcript, embedding, and storing..."
          : "Inspecting, downloading, normalizing, embedding, and storing...",
    );
    try {
      const result = await request(
        urlContentType === "article" ? "/content/url" : `/content/${urlContentType}`,
        {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          ...(contentTitle.trim() && { title: contentTitle.trim() }),
          ...(urlContentType === "podcast" && transcript && { transcript }),
          ...(urlContentType === "podcast" && transcriptUrl && { transcript_url: transcriptUrl }),
        }),
        },
      );
      setContentStatus(`Saved ${result.article.title} with ${result.chunk_count} chunks.`);
      setContentUrl("");
      setPodcastTranscript("");
      setPodcastTranscriptUrl("");
      setContentTitle("");
      await loadArticles();
    } catch (error) {
      setContentStatus(`Could not add ${urlContentType}: ${errorMessage(error)}`);
    } finally {
      setIsAddingUrl(false);
    }
  }

  async function handleAsk(event) {
    event.preventDefault();
    const normalizedQuestion = question.trim();
    if (!normalizedQuestion) return;

    setIsAsking(true);
    try {
      let activeConversationId = conversationId;
      if (!activeConversationId) {
        const conversation = await request("/conversations", { method: "POST" });
        activeConversationId = conversation.id;
        setConversationId(activeConversationId);
      }
      const result = await request(`/conversations/${activeConversationId}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: normalizedQuestion }),
      });
      setChatMessages(result.messages);
      setQuestion("");
    } catch (error) {
      setChatMessages((current) => [...current, {
        id: `error-${Date.now()}`,
        role: "assistant",
        content: `Question failed: ${errorMessage(error)}`,
      }]);
    } finally {
      setIsAsking(false);
    }
  }

  async function handleDelete(article) {
    const confirmed = window.confirm(`Delete \"${article.title}\"? This cannot be undone.`);
    if (!confirmed) return;

    setDeletingArticleId(article.id);
    setArticleError("");
    try {
      await request(`/articles/${article.id}`, { method: "DELETE" });
      const result = await loadArticles();
      if (showAllArticles && result?.items.length === 0 && libraryPage > 0) {
        setLibraryPage((page) => page - 1);
      }
    } catch (error) {
      setArticleError(`Could not delete article: ${errorMessage(error)}`);
    } finally {
      setDeletingArticleId("");
    }
  }

  return (
    <main className="shell">
      <header className="masthead">
        <a className="wordmark" href="#/">Signal Cabinet</a>
        <p className="eyebrow">PERSONAL TECH WATCH / LOCAL RAG</p>
        <p className="intro">Collect the signal, then ask your library what it knows.</p>
        <nav aria-label="Workspace" className="masthead-links"><a href="#/conversations">History</a><a href="#/drafts">Drafts</a></nav>
      </header>

      {isDraftsPage ? <DraftsPage /> : isConversationsPage ? <ConversationHistoryPage onEditArticle={(articleId) => {
        setEditingArticleId(articleId);
        window.location.hash = "#/";
      }} onOpen={(conversation) => {
        setConversationId(conversation.id);
        setChatMessages(conversation.messages);
        window.location.hash = "#/";
      }} /> : <>
      {!showAllArticles && <TopicDiscovery
        categories={discoveryCategories}
        isLoading={isDiscovering}
        onCategoryChange={handleDiscoveryCategory}
        onCollect={handleCollectDiscoveredTopic}
        onRefresh={() => loadDiscovery()}
        status={discoveryStatus}
        topics={discoveryTopics}
      />}

      {!showAllArticles && <section className="watch-panel" aria-labelledby="watch-title">
        <div>
          <p className="section-number">01B / COLLECT</p>
          <h1 id="watch-title">Watch a topic.</h1>
        </div>
        <div className="collect-forms">
          <form className="watch-form" onSubmit={handleWatch}>
            <label htmlFor="watch-topic">Search the web for a topic</label>
            <div className="input-row">
              <input id="watch-topic" maxLength="200" minLength="1" onChange={(event) => setTopic(event.target.value)} placeholder="AI agents" required value={topic} />
              <button disabled={isWatching} type="submit">{isWatching ? "Collecting..." : "Collect"}</button>
            </div>
            <p className="status" aria-live="polite">{watchStatus}</p>
          </form>

          <form className="content-form" onSubmit={handleAddContent}>
            <p className="content-form-title">Or add content</p>
            <label className="sr-only" htmlFor="content-title">Title</label>
            <input id="content-title" maxLength="500" onChange={(event) => setContentTitle(event.target.value)} placeholder="Title (optional)" value={contentTitle} />
            <label className="sr-only" htmlFor="content-source-url">Original source</label>
            <input id="content-source-url" onChange={(event) => setContentSourceUrl(event.target.value)} placeholder="Original source (URL, name, or personal note)" value={contentSourceUrl} />
            <div className="content-composer" onPaste={handleContentPaste}>
              <label className="sr-only" htmlFor="content-text">Text to add</label>
              <textarea disabled={Boolean(contentFile)} id="content-text" maxLength="100000" onChange={(event) => setContentText(event.target.value)} placeholder={contentFile ? "Remove the attached file to paste text." : "Paste a note, article, transcript, or image..."} rows="4" value={contentText} />
              <div className="composer-footer">
                <label className="attach-file" htmlFor="content-file">
                  Attach file
                  <input accept="text/*,.md,.markdown,.html,.htm,.csv,application/pdf,.pdf,image/*" id="content-file" onChange={(event) => setContentFile(event.target.files?.[0] || null)} ref={fileInputRef} type="file" />
                </label>
                <span>Paste text, or paste an image/file with Cmd/Ctrl+V.</span>
              </div>
            </div>
            <FilePreview
              file={contentFile}
              imagePreviewUrl={imagePreviewUrl}
              onClear={clearContentFile}
            />
            <div className="url-add-row">
              <label className="sr-only" htmlFor="url-content-type">Content type</label>
              <select id="url-content-type" onChange={(event) => setUrlContentType(event.target.value)} value={urlContentType}>
                <option value="article">Article URL</option>
                <option value="youtube">YouTube video</option>
                <option value="podcast">Podcast episode</option>
              </select>
              <label className="sr-only" htmlFor="content-url">URL to ingest</label>
              <input id="content-url" onChange={(event) => setContentUrl(event.target.value)} onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  handleAddUrl();
                }
              }} placeholder={urlContentType === "article" ? "https://example.com/article" : urlContentType === "youtube" ? "YouTube video URL with captions" : "Podcast episode URL"} type="url" value={contentUrl} />
              <button disabled={isAddingContent || isAddingUrl} onClick={handleAddUrl} type="button">{isAddingUrl ? "Adding..." : "Add URL"}</button>
            </div>
            {urlContentType === "podcast" && <div className="podcast-transcript-panel">
                <p>Optional: paste a transcript or link one. Leave both blank to find a public feed and transcribe its audio locally.</p>
                <textarea aria-label="Podcast transcript" disabled={Boolean(podcastTranscriptUrl)} maxLength="500000" onChange={(event) => setPodcastTranscript(event.target.value)} placeholder="Paste a transcript instead of automatic transcription..." rows="4" value={podcastTranscript} />
                <input aria-label="Podcast transcript URL" disabled={Boolean(podcastTranscript)} onChange={(event) => setPodcastTranscriptUrl(event.target.value)} placeholder="Or link a publisher transcript page" type="url" value={podcastTranscriptUrl} />
            </div>}
            <button disabled={isAddingContent || isAddingUrl} type="submit">{isAddingContent ? "Adding..." : "Add to library"}</button>
            <p className="status" aria-live="polite">{contentStatus}</p>
          </form>
        </div>
      </section>}

      <section className="library-panel" aria-labelledby="library-title">
        <div className="section-heading">
          <div>
            <p className="section-number">02 / LIBRARY</p>
            <h2 id="library-title">{showAllArticles ? "All articles" : "Latest articles"}</h2>
          </div>
          <div className="library-heading-actions">
            <p className="count" aria-live="polite">{articles !== null ? `${articleTotal} saved` : ""}</p>
            {showAllArticles ? (
              <a className="library-link" href="#/">Dashboard</a>
            ) : (
              <a className="library-link" href="#/articles">View all</a>
            )}
          </div>
        </div>
        <div className="article-list" aria-live="polite">
          <ArticleList
            articles={articles}
            deletingArticleId={deletingArticleId}
            error={articleError}
            onDelete={handleDelete}
            onEdit={setEditingArticleId}
          />
        </div>
        {showAllArticles && (
          <Pagination
            currentPage={libraryPage}
            onNext={() => setLibraryPage((page) => page + 1)}
            onPrevious={() => setLibraryPage((page) => page - 1)}
            total={articleTotal}
          />
        )}
      </section>

      {!showAllArticles && <section className="ask-panel" aria-labelledby="ask-title">
        <div className="ask-copy">
          <p className="section-number">03 / ASK</p>
          <h2 id="ask-title">Ask the cabinet.</h2>
          <p>Answers are grounded in the articles you collected. This discussion is saved locally.</p>
          <div className="ask-links"><a className="library-link" href="#/conversations">Open history</a><button className="close-button" onClick={() => { setConversationId(""); setChatMessages([]); }} type="button">New conversation</button></div>
        </div>
        <div className="chat-stage">
          <img alt="Illustration of two cats around a chat box" className="chatbox-art" src="/assets/chatbox.png" />
          <div className="chat-content">
            <div className="chat-history" aria-live="polite">
              {chatMessages.length === 0 ? <p className="empty-chat">What do you want to know?</p> : chatMessages.map((message) => <div className={`chat-message ${message.role}`} key={message.id}><span>{message.role === "user" ? "You" : "Cabinet"}</span><p><MessageContent content={message.content} onEditArticle={setEditingArticleId} role={message.role} /></p></div>)}
              {isAsking && <div aria-label="Cabinet is thinking" className="chat-message assistant is-loading" role="status"><span>Cabinet</span><p>Thinking<span className="loading-dots" aria-hidden="true"><i></i><i></i><i></i></span></p></div>}
            </div>
            <form className="ask-form" onSubmit={handleAsk}>
              <label className="sr-only" htmlFor="question">Your question</label>
              <textarea id="question" maxLength="1000" minLength="1" onChange={(event) => setQuestion(event.target.value)} placeholder="What should I understand about AI agents?" required rows="2" value={question} />
              <button disabled={isAsking} type="submit">{isAsking ? "Thinking..." : "Ask"}</button>
            </form>
          </div>
        </div>
      </section>}

      <DraftComposer
        onCreated={() => { window.location.hash = "#/drafts"; }}
      />
      {editingArticleId && (
        <ArticleEditor
          articleId={editingArticleId}
          onClose={() => setEditingArticleId("")}
          onSaved={loadArticles}
        />
      )}
      </>}
    </main>
  );
}
