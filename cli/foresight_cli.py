#!/usr/bin/env python3
"""Foresight Python CLI - reuses backend data services for data downloading, processing, and inspection."""
import argparse
import asyncio
import sys
import json
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.markets import get_market, markets, primary_market, source_for
from backend.app.processor import DatasetProcessor
from backend.app.splits import calculate_split_summaries
from backend.app.validator import validate_dataset


def print_banner():
    print("=" * 60)
    print("  FORESIGHT | Cryptocurrency Historical Data Engine CLI")
    print("=" * 60)


async def cmd_download(symbol: str, concurrency: int):
    print(f"\n[*] Starting archive download for {symbol}...")
    market = get_market(symbol)
    downloader = source_for(market).downloader(market, max_concurrency=concurrency)

    def on_progress(p):
        print(
            f"\r[{p['percent']}%] Downloaded {p['completed_files']}/{p['total_files']} files ({p['current_file']})",
            end="",
            flush=True,
        )

    res = await downloader.download_all(progress_callback=on_progress)
    if res["verified"] != res["total"]:
        raise ValueError("Not all required archives verified; retry to resume")
    print(
        f"\n[+] Download completed: {res['verified']} verified files. Manifest saved to {res['manifest_path']}"
    )


def cmd_process(symbol: str):
    print(f"\n[*] Processing and validating {symbol}...")
    processor = DatasetProcessor(symbol)

    def on_progress(p):
        print(
            f"\r[{p['percent']}%] {p['status'].title()}: {p['current_file']}",
            end="",
            flush=True,
        )

    # Check cross market
    cross_df = None
    cross_market = get_market(symbol).cross_market
    if cross_market:
        other_proc = DatasetProcessor(cross_market)
        cross_df = other_proc.load_processed()

    res = processor.process_and_save(
        cross_market_df=cross_df, progress_callback=on_progress
    )
    print(f"\n[+] Processing completed!")
    print(f"    Total rows: {res['total_rows']}")
    print(f"    Parquet file: {res['parquet_path']}")
    print(
        f"    Quality status: {res['quality_report']['status'].upper()} (Verified: {res['quality_report']['is_verified']})"
    )


def cmd_inspect(symbol: str):
    processor = DatasetProcessor(symbol)
    df = processor.load_processed()
    report = processor.load_quality_report()

    if df is None or df.empty:
        print(
            f"[-] No processed data found for {symbol}. Run `python cli/foresight_cli.py import --symbol {symbol}` first."
        )
        return

    print_banner()
    print(f"Dataset Symbol:     {symbol}")
    print(f"Total Rows:         {len(df):,}")
    print(f"Coverage Start:     {df['open_time'].min()}")
    print(f"Coverage End:       {df['open_time'].max()}")
    print(f"Parquet Path:       {processor.parquet_path}")

    print("\n[Chronological Splits]")
    splits = calculate_split_summaries(df, get_market(symbol).splits)
    for k, s in splits.items():
        print(
            f"  • {s['label']:<12} | {s['date_label']:<22} | {s['actual_count']:,} rows ({s['percentage']}%) | {s['duration_months']} months"
        )

    print("\n[Quality Report]")
    if report:
        print(f"  Status:             {report.get('status').upper()}")
        print(f"  Verified:           {report.get('is_verified')}")
        print(f"  Missing Hours:      {report.get('missing_hours_count')}")
        print(f"  Duplicates:         {report.get('duplicate_count')}")
        print(f"  Invalid OHLC:       {report.get('invalid_ohlc_count')}")
        print(f"  Non-Positive Price: {report.get('non_positive_price_count')}")
        print(f"  Negative Volume:    {report.get('negative_volume_count')}")
        print(f"  Hourly Aligned:     {report.get('timestamp_alignment_valid')}")
        if report.get("cross_market_aligned") is not None:
            print(f"  Cross-Market Align: {report.get('cross_market_aligned')}")


def cmd_export(symbol: str, out_path: str, split: str = None):
    processor = DatasetProcessor(symbol)
    df = processor.load_processed()
    if df is None or df.empty:
        print(f"[-] No data found for {symbol}")
        return

    filtered = df
    if split and split != "all":
        filtered = filtered[filtered["split"] == split]

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    filtered.to_csv(out, index=False)
    print(f"[+] Exported {len(filtered)} rows to {out}")


def main():
    parser = argparse.ArgumentParser(
        description="Foresight Historical Cryptocurrency Data Engine CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    SUPPORTED_SYMBOLS = [m.symbol for m in markets()]
    PRIMARY_SYMBOL = primary_market().symbol

    subparsers.add_parser("markets", help="List registered markets and their rules")

    # Download
    dl_parser = subparsers.add_parser(
        "download", help="Download Binance raw monthly archives"
    )
    dl_parser.add_argument(
        "--symbol", choices=SUPPORTED_SYMBOLS, default=PRIMARY_SYMBOL
    )
    dl_parser.add_argument(
        "--all", action="store_true", help="Download all supported symbols"
    )
    dl_parser.add_argument("--concurrency", type=int, default=4)

    # Process
    proc_parser = subparsers.add_parser(
        "process", help="Parse, normalize, split and validate archives"
    )
    proc_parser.add_argument(
        "--symbol", choices=SUPPORTED_SYMBOLS, default=PRIMARY_SYMBOL
    )
    proc_parser.add_argument(
        "--all", action="store_true", help="Process all supported symbols"
    )

    # Import (download + process)
    imp_parser = subparsers.add_parser(
        "import", help="Run full download and process pipeline"
    )
    imp_parser.add_argument(
        "--symbol", choices=SUPPORTED_SYMBOLS, default=PRIMARY_SYMBOL
    )
    imp_parser.add_argument(
        "--all", action="store_true", help="Import all supported symbols"
    )
    imp_parser.add_argument("--concurrency", type=int, default=4)

    # Inspect
    insp_parser = subparsers.add_parser(
        "inspect", help="Inspect processed dataset and quality report"
    )
    insp_parser.add_argument(
        "--symbol", choices=SUPPORTED_SYMBOLS, default=PRIMARY_SYMBOL
    )

    # Export
    exp_parser = subparsers.add_parser("export", help="Export dataset to CSV")
    exp_parser.add_argument(
        "--symbol", choices=SUPPORTED_SYMBOLS, default=PRIMARY_SYMBOL
    )
    exp_parser.add_argument("--out", required=True, help="Output CSV path")
    exp_parser.add_argument(
        "--split",
        choices=["training", "validation", "final_test", "all"],
        default="all",
    )

    train_parser = subparsers.add_parser(
        "train-backtest", help="Train and replay shared numerical services"
    )
    train_parser.add_argument(
        "--mode", choices=["frozen", "adaptive"], default="frozen"
    )
    train_parser.add_argument(
        "--lookbacks",
        type=int,
        nargs="+",
        choices=[30, 90, 180],
        default=[30, 90, 180],
        help="Look-back candidates compared on development data",
    )
    train_parser.add_argument(
        "--alphas",
        type=float,
        nargs="+",
        default=[1.0, 10.0, 100.0],
        help="Ridge penalty candidates",
    )
    compare_parser = subparsers.add_parser(
        "compare",
        help="Train the configured model families, pick the winner on validation, final-test it once",
    )
    compare_parser.add_argument(
        "--families",
        nargs="+",
        default=None,
        help="Override FORESIGHT_COMPARISON_FAMILIES (default Ridge, LightGBM, KNN)",
    )
    compare_parser.add_argument(
        "--origin",
        default=None,
        help="Explicit UTC ISO forecast origin; default latest observed completed candle",
    )
    predict_parser = subparsers.add_parser(
        "predict", help="Publish an immutable seven-day forecast"
    )
    predict_parser.add_argument(
        "--origin",
        default=None,
        help="Explicit UTC ISO origin; default latest observed completed candle",
    )
    predict_parser.add_argument("--model", default=None)
    evaluate_parser = subparsers.add_parser(
        "evaluate", help="Score exact matured target outcomes"
    )
    evaluate_parser.add_argument("--forecast", required=True)
    evaluate_parser.add_argument(
        "--clock", required=True, help="Explicit simulated UTC evaluation cutoff"
    )
    history_parser = subparsers.add_parser(
        "history", help="List stored coordinated forecasts"
    )
    history_parser.add_argument("--run", default=None)
    history_parser.add_argument(
        "--mode", choices=["frozen", "adaptive", "prediction"], default=None
    )
    history_parser.add_argument("--model", default=None)
    history_parser.add_argument("--page", type=int, default=1)
    history_parser.add_argument("--page-size", type=int, default=50)
    subparsers.add_parser("runs", help="List replay runs and their labels")
    agents_parser = subparsers.add_parser(
        "agents", help="Show agent states for a forecast or run"
    )
    agents_parser.add_argument("--forecast", default=None)
    agents_parser.add_argument("--run", default=None)
    subparsers.add_parser("models", help="List saved model versions")
    metrics_parser = subparsers.add_parser(
        "metrics", help="Export run evaluation with sample counts"
    )
    metrics_parser.add_argument("--run", required=True)
    retrain_parser = subparsers.add_parser(
        "retrain",
        help="Train earlier-data candidate and apply declared promotion policy",
    )
    retrain_parser.add_argument("--model", required=True)
    retrain_parser.add_argument("--cutoff", required=True)
    rollback_parser = subparsers.add_parser(
        "rollback", help="Select an earlier saved model"
    )
    rollback_parser.add_argument("--model", required=True)

    args = parser.parse_args()

    if args.command in {
        "train-backtest",
        "compare",
        "predict",
        "evaluate",
        "history",
        "models",
        "metrics",
        "retrain",
        "rollback",
        "runs",
        "agents",
    }:
        from backend.app.forecasting.service import Engine
        from backend.app.forecasting.evaluator import aggregate

        engine = Engine()
        if args.command == "train-backtest":
            result = engine.train_backtest(
                {"mode": args.mode, "lookbacks": args.lookbacks, "alphas": args.alphas}
            )
        elif args.command == "compare":
            from backend.app.forecasting.comparison import run_comparison

            run_id = run_comparison(engine, args.origin, families=args.families)[
                "comparison_id"
            ]
            run = engine.store.get("runs", run_id)
            winner = run["models"][0]
            result = {
                "comparison_id": run_id,
                "evaluation_label": run["evaluation_label"],
                "validation_selection": run["validation_selection"],
                "final_test": {
                    "family": winner["family"],
                    "model_id": winner["model_id"],
                    "horizons": winner["metrics"]["horizons"],
                },
            }
        elif args.command == "predict":
            result = engine.predict(args.origin, args.model)
        elif args.command == "evaluate":
            result = engine.evaluate_at(args.forecast, args.clock)
        elif args.command == "history":
            result = engine.history(
                args.page, args.page_size, args.run, args.mode, args.model
            )
        elif args.command == "runs":
            result = engine.runs()
        elif args.command == "agents":
            result = engine.agent_status(forecast_id=args.forecast, run_id=args.run)
        elif args.command == "models":
            result = [
                {
                    k: m[k]
                    for k in (
                        "id",
                        "configuration",
                        "training_cutoff",
                        "counts",
                        "selected",
                        "uses_final_test_outcomes",
                    )
                }
                for m in engine.models()
            ]
        elif args.command == "metrics":
            result = {
                "coordinated": aggregate(engine.store, args.run),
                "specialist": aggregate(engine.store, args.run, "specialist"),
            }
        elif args.command == "retrain":
            result = engine.retrain(args.model, args.cutoff)
        else:
            result = engine.rollback(args.model)
        print(json.dumps(result, indent=2))
    elif args.command == "markets":
        print(json.dumps([m.summary() for m in markets()], indent=2))
    elif args.command == "download":
        symbols = SUPPORTED_SYMBOLS if args.all else [args.symbol]
        for s in symbols:
            asyncio.run(cmd_download(s, args.concurrency))
    elif args.command == "process":
        symbols = SUPPORTED_SYMBOLS if args.all else [args.symbol]
        for s in symbols:
            cmd_process(s)
    elif args.command == "import":
        symbols = SUPPORTED_SYMBOLS if args.all else [args.symbol]
        for s in symbols:
            asyncio.run(cmd_download(s, args.concurrency))
            cmd_process(s)
    elif args.command == "inspect":
        cmd_inspect(args.symbol)
    elif args.command == "export":
        cmd_export(args.symbol, args.out, args.split)


if __name__ == "__main__":
    main()
