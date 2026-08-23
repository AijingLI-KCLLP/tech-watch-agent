import argparse

from services.agent_service import (
    ask_question,
    categorize_existing_articles,
    qualify_existing_sources,
    tag_existing_articles,
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
    update_count = result["would_update"] if dry_run else result["updated"]
    print(
        f"Processed {result['processed']} articles; {mode} {update_count}; "
        f"kept {result['kept_inbox']} in inbox."
    )
    for failure in result["failed"]:
        print(f"Failed {failure['id']}: {failure['error']}")


def cmd_qualify(*, dry_run: bool) -> None:
    result = qualify_existing_sources(dry_run=dry_run)
    mode = "would update" if dry_run else "updated"
    print(
        f"Processed {result['processed']} source URLs; qualified "
        f"{result['qualified_sources']}; {mode} {result['updated_rows']} rows; "
        f"left {result['unqualified_sources']} unqualified."
    )


def cmd_tag(*, dry_run: bool, replace: bool) -> None:
    result = tag_existing_articles(dry_run=dry_run, replace=replace)
    if dry_run:
        print(
            f"Processed {result['processed']} articles; generated "
            f"{result['generated_tags']} tag candidates (dry run)."
        )
    else:
        print(
            f"Processed {result['processed']} articles; generated "
            f"{result['generated_tags']} tags and added "
            f"{result['added_tag_links']} new tag links."
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

    p_qualify = sub.add_parser(
        "qualify",
        help="Qualify existing source URLs with LM Studio",
    )
    p_qualify.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate sources without writing credibility fields",
    )

    p_tag = sub.add_parser("tag", help="Generate tags for existing articles with LM Studio")
    p_tag.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate tags without adding them to articles",
    )
    p_tag.add_argument(
        "--replace",
        action="store_true",
        help="Replace all existing tags for each article (including manual/topic tags)",
    )

    args = parser.parse_args()
    if args.cmd == "watch":
        cmd_watch(args.topic)
    elif args.cmd == "ask":
        cmd_ask(args.question)
    elif args.cmd == "categorize":
        cmd_categorize(all_articles=args.all, dry_run=args.dry_run)
    elif args.cmd == "qualify":
        cmd_qualify(dry_run=args.dry_run)
    elif args.cmd == "tag":
        cmd_tag(dry_run=args.dry_run, replace=args.replace)


if __name__ == "__main__":
    main()
