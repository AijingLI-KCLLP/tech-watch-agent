import { useEffect, useState } from "react";

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
      {article.url ? (
        <a className="article-title" href={article.url} rel="noreferrer" target="_blank">
          {article.title}
        </a>
      ) : (
        <span className="article-title">{article.title}</span>
      )}
      <div className="article-actions">
        <p className="article-meta">
          {article.source_name || "unknown source"} / {formatArticleDate(article.fetched_at)} / {article.n_tags} tags
        </p>
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

export default function App() {
  const [articles, setArticles] = useState(null);
  const [articleError, setArticleError] = useState("");
  const [topic, setTopic] = useState("");
  const [watchStatus, setWatchStatus] = useState("");
  const [isWatching, setIsWatching] = useState(false);
  const [deletingArticleId, setDeletingArticleId] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("Ask a question to begin.");
  const [isAsking, setIsAsking] = useState(false);

  async function loadArticles() {
    setArticleError("");
    try {
      setArticles(await request("/articles"));
    } catch (error) {
      setArticleError(errorMessage(error));
    }
  }

  useEffect(() => {
    loadArticles();
  }, []);

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
      await loadArticles();
    } catch (error) {
      setArticleError(`Could not delete article: ${errorMessage(error)}`);
    } finally {
      setDeletingArticleId("");
    }
  }

  return (
    <main className="shell">
      <header className="masthead">
        <a className="wordmark" href="/">Signal Cabinet</a>
        <p className="eyebrow">PERSONAL TECH WATCH / LOCAL RAG</p>
        <p className="intro">Collect the signal, then ask your library what it knows.</p>
      </header>

      <section className="watch-panel" aria-labelledby="watch-title">
        <div>
          <p className="section-number">01 / COLLECT</p>
          <h1 id="watch-title">Watch a topic.</h1>
        </div>
        <form className="watch-form" onSubmit={handleWatch}>
          <label htmlFor="watch-topic">Topic to research</label>
          <div className="input-row">
            <input id="watch-topic" maxLength="200" minLength="1" onChange={(event) => setTopic(event.target.value)} placeholder="AI agents" required value={topic} />
            <button disabled={isWatching} type="submit">{isWatching ? "Collecting..." : "Collect"}</button>
          </div>
          <p className="status" aria-live="polite">{watchStatus}</p>
        </form>
      </section>

      <section className="library-panel" aria-labelledby="library-title">
        <div className="section-heading">
          <div>
            <p className="section-number">02 / LIBRARY</p>
            <h2 id="library-title">Articles</h2>
          </div>
          <p className="count" aria-live="polite">{articles ? `${articles.length} saved` : ""}</p>
        </div>
        <div className="article-list" aria-live="polite">
          <ArticleList
            articles={articles}
            deletingArticleId={deletingArticleId}
            error={articleError}
            onDelete={handleDelete}
          />
        </div>
      </section>

      <section className="ask-panel" aria-labelledby="ask-title">
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
      </section>
    </main>
  );
}
