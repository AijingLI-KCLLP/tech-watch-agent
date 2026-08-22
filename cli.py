import argparse

from services.agent_service import ask_question, watch_topic


def cmd_watch(topic: str) -> None:
    result = watch_topic(topic)
    print(
        f"Ingested {result['article_count']} articles "
        f"({result['chunk_count']} chunks for topic: {result['topic']}!r)"
    )

def cmd_ask(question: str) -> None:
    result = ask_question(question)
    print(result["answer"])


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
