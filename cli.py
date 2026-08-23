import argparse

from services.agent_service import (
    ask_question,
    categorize_existing_articles,
    watch_topic,
)


def cmd_watch(topic: str) -> None:
    result = watch_topic(topic)
    print(
        f"Ingested {result['article_count']} articles "
        f"({result['chunk_count']} chunks for topic: {result['topic']}!r)"
    )

def cmd_ask(question: str) -> None:
    result = ask_question(question)
    print(result["answer"])


def cmd_categorize(*, all_articles: bool, dry_run: bool) -> None:
    result = categorize_existing_articles(
        only_inbox=not all_articles,
        dry_run=dry_run,
    )
    mode = "would update" if dry_run else "updated"
    print(
        f"Processed {result['processed']} articles; {mode} {result['updated']}; "
        f"kept {result['kept_inbox']} in inbox."
    )
    for failure in result["failed"]:
        print(f"Failed {failure['id']}: {failure['error']}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="tech_watch_agent")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_watch = sub.add_parser("watch", help="Ingest articles for a topic")
    p_watch.add_argument("topic", type=str)

    p_ask = sub.add_parser("ask", help="Ask a question against ingested articles")
    p_ask.add_argument("question", type=str)

    p_categorize = sub.add_parser(
        "categorize",
        help="Categorize existing inbox articles with LM Studio",
    )
    p_categorize.add_argument(
        "--all",
        action="store_true",
        help="Re-categorize articles that may already have been manually reviewed",
    )
    p_categorize.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify without writing category changes",
    )

    args = parser.parse_args()
    if args.cmd == "watch":
        cmd_watch(args.topic)
    elif args.cmd == "ask":
        cmd_ask(args.question)
    elif args.cmd == "categorize":
        cmd_categorize(all_articles=args.all, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
