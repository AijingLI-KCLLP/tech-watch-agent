import { useEffect, useRef, useState } from "react";

const DASHBOARD_ARTICLE_LIMIT = 10;
const LIBRARY_PAGE_SIZE = 20;

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

function ArticleList({ articles, deletingArticleId, error, onDelete }) {
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
      <div className="article-actions">
        <p className="article-meta">
          {article.source_name || "unknown source"} / {formatArticleDate(article.fetched_at)} / {article.n_tags} tags
        </p>
        {article.raw_file_url && (
          <a className="raw-file-link" href={article.raw_file_url} rel="noreferrer" target="_blank">Raw image</a>
        )}
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

function isAllArticlesPage() {
  return window.location.hash === "#/articles";
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
  const [showAllArticles, setShowAllArticles] = useState(isAllArticlesPage);
  const [libraryPage, setLibraryPage] = useState(0);
  const [topic, setTopic] = useState("");
  const [watchStatus, setWatchStatus] = useState("");
  const [isWatching, setIsWatching] = useState(false);
  const [contentText, setContentText] = useState("");
  const [contentFile, setContentFile] = useState(null);
  const [imagePreviewUrl, setImagePreviewUrl] = useState("");
  const [contentTitle, setContentTitle] = useState("");
  const [contentSourceUrl, setContentSourceUrl] = useState("");
  const [articleUrl, setArticleUrl] = useState("");
  const [contentStatus, setContentStatus] = useState("");
  const [isAddingContent, setIsAddingContent] = useState(false);
  const [isAddingUrl, setIsAddingUrl] = useState(false);
  const [deletingArticleId, setDeletingArticleId] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("Ask a question to begin.");
  const [isAsking, setIsAsking] = useState(false);
  const fileInputRef = useRef(null);

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
      setShowAllArticles(isAllArticlesPage());
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

  async function handleWatch(event) {
    event.preventDefault();
    const normalizedTopic = topic.trim();
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

  async function handleAddContent(event) {
    event.preventDefault();
    const title = contentTitle.trim();
    const providedSourceUrl = contentSourceUrl.trim();

    setIsAddingContent(true);
    setContentStatus("Transcribing, normalizing, embedding, and storing...");
    try {
      let result;
      if (contentFile) {
        const formData = new FormData();
        formData.append("file", contentFile);
        if (title) formData.append("title", title);
        if (providedSourceUrl) formData.append("provided_source_url", providedSourceUrl);
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
    const url = articleUrl.trim();
    if (!url) {
      setContentStatus("Enter an article URL first.");
      return;
    }

    setIsAddingUrl(true);
    setContentStatus("Inspecting, downloading, normalizing, embedding, and storing...");
    try {
      const result = await request("/content/url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          ...(contentTitle.trim() && { title: contentTitle.trim() }),
        }),
      });
      setContentStatus(`Saved ${result.article.title} with ${result.chunk_count} chunks. Source: verified.`);
      setArticleUrl("");
      setContentTitle("");
      await loadArticles();
    } catch (error) {
      setContentStatus(`Could not add URL: ${errorMessage(error)}`);
    } finally {
      setIsAddingUrl(false);
    }
  }

  async function handleAsk(event) {
    event.preventDefault();
    const normalizedQuestion = question.trim();
    if (!normalizedQuestion) return;

    setIsAsking(true);
    setAnswer("Searching the cabinet...");
    try {
      const result = await request("/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: normalizedQuestion }),
      });
      setAnswer(result.answer);
    } catch (error) {
      setAnswer(`Question failed: ${errorMessage(error)}`);
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
      </header>

      {!showAllArticles && <section className="watch-panel" aria-labelledby="watch-title">
        <div>
          <p className="section-number">01 / COLLECT</p>
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
            <label className="sr-only" htmlFor="content-source-url">Source URL</label>
            <input id="content-source-url" onChange={(event) => setContentSourceUrl(event.target.value)} placeholder="Original source URL (optional)" type="url" value={contentSourceUrl} />
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
              <label className="sr-only" htmlFor="article-url">Article URL to ingest</label>
              <input id="article-url" onChange={(event) => setArticleUrl(event.target.value)} onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  handleAddUrl();
                }
              }} placeholder="Add article by URL: https://example.com/article" type="url" value={articleUrl} />
              <button disabled={isAddingContent || isAddingUrl} onClick={handleAddUrl} type="button">{isAddingUrl ? "Adding URL..." : "Add URL"}</button>
            </div>
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
          <p>Answers are grounded in the articles you collected, with source IDs included where available.</p>
        </div>
        <div className="chat-stage">
          <img alt="Illustration of two cats around a chat box" className="chatbox-art" src="/assets/chatbox.png" />
          <div className="chat-content">
            <div className="answer" aria-live="polite">{answer}</div>
            <form className="ask-form" onSubmit={handleAsk}>
              <label className="sr-only" htmlFor="question">Your question</label>
              <textarea id="question" maxLength="1000" minLength="1" onChange={(event) => setQuestion(event.target.value)} placeholder="What should I understand about AI agents?" required rows="2" value={question} />
              <button disabled={isAsking} type="submit">{isAsking ? "Thinking..." : "Ask"}</button>
            </form>
          </div>
        </div>
      </section>}
    </main>
  );
}
