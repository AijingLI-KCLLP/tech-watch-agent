import argparse

from adapters.store import init_db
from core.ingest_graph import build_ingest_graph
from core.retrieve_graph import build_retrieve_graph


def cmd_watch(topic: str) -> None:
    init_db()
    graph = build_ingest_graph()
    final = graph.invoke({"topic": topic})
    print(
        f"Ingested {len(final['articles'])} articles "
        f"({len(final['chunks'])} chunks) for topic: {topic!r}"
    )


def cmd_ask(question: str) -> None:
    graph = build_retrieve_graph()
    final = graph.invoke({"question": question})
    print(final["answer"])


def main() -> None:
    parser = argparse.ArgumentParser(prog="tech_watch_agent")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_watch = sub.add_parser("watch", help="Ingest articles for a topic")
    p_watch.add_argument("topic", type=str)

    p_ask = sub.add_parser("ask", help="Ask a question against ingested articles")
    p_ask.add_argument("question", type=str)

    args = parser.parse_args()
    if args.cmd == "watch":
        cmd_watch(args.topic)
    elif args.cmd == "ask":
        cmd_ask(args.question)


if __name__ == "__main__":
    main()
