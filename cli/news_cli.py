#!/usr/bin/env python3
"""News commands use the same services as desktop API; no external call on reads."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.app.news.service import NewsService
from backend.app.news.contracts import ImportRequest, PacketRequest, ClassifyRequest, ForecastExperimentRequest, LabelRequest
from backend.app.storage import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, help='Optional isolated SQLite database')
    parser.add_argument('--root', type=Path, help='Optional isolated artifact root')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    p = commands.add_parser('import'); p.add_argument('file', type=Path); p.add_argument('--provider', default='local')
    p = commands.add_parser('collect'); p.add_argument('--source', default='federal-reserve')
    p = commands.add_parser('packet'); p.add_argument('--symbol', default='BTCUSDT'); p.add_argument('--origin', required=True); p.add_argument('--lookback-days', type=int, default=7); p.add_argument('--policy', choices=['strict','exploratory'], default='strict')
    for command in ('preview', 'classify'):
        p = commands.add_parser(command); p.add_argument('packet_id'); p.add_argument('--classifier', choices=['keywords','jev','openai'], default='keywords'); p.add_argument('--budget-usd', type=float, default=0); p.add_argument('--max-articles', type=int, default=100)
    p = commands.add_parser('features'); p.add_argument('packet_id'); p.add_argument('--classifier', choices=['keywords','jev','openai'], default='keywords')
    p = commands.add_parser('label'); p.add_argument('file', type=Path)
    p = commands.add_parser('evaluate'); p.add_argument('packet_id'); p.add_argument('--classifier', choices=['jev','openai'], default='jev')
    p = commands.add_parser('train'); p.add_argument('--symbol', default='BTCUSDT'); p.add_argument('--policy', choices=['strict','exploratory'], default='strict'); p.add_argument('--evidence-lookback-days', type=int, default=7)
    p = commands.add_parser('predict'); p.add_argument('model_id'); p.add_argument('--origin')
    p = commands.add_parser('read'); p.add_argument('kind'); p.add_argument('id')
    args = parser.parse_args()
    service = NewsService(Store(args.database), root=args.root)
    if args.command == 'status': result = service.status()
    elif args.command == 'import':
        if args.file.stat().st_size > 2_000_000: parser.error('Import at most 2MB per batch')
        text = args.file.read_text()
        rows = [json.loads(line) for line in text.splitlines() if line.strip()] if args.file.suffix == '.jsonl' else json.loads(text)
        req = ImportRequest(provider=args.provider, articles=rows if isinstance(rows,list) else rows['articles'])
        result = service.ingest(req.articles, req.provider)
    elif args.command == 'collect': result = service.collect(args.source)
    elif args.command == 'packet':
        req = PacketRequest(symbol=args.symbol, origin=args.origin, lookback_days=args.lookback_days, policy=args.policy)
        result = service.packet(**req.model_dump())
    elif args.command in ('preview', 'classify'):
        req = ClassifyRequest(packet_id=args.packet_id, classifier=args.classifier, budget_usd=args.budget_usd, max_articles=args.max_articles)
        result = service.preview(req.packet_id, req.classifier, req.max_articles) if args.command == 'preview' else service.classify(**req.model_dump())
    elif args.command == 'features': result = service.features(service.records.get('packet',args.packet_id),args.classifier)
    elif args.command == 'label': result = service.label(LabelRequest.model_validate_json(args.file.read_text()).model_dump())
    elif args.command == 'evaluate': result = service.classification_evaluation(args.packet_id,args.classifier)
    elif args.command == 'train':
        from backend.app.news.forecasting import experiment
        from backend.app.forecasting.data import MarketData
        req = ForecastExperimentRequest(symbol=args.symbol, policy=args.policy, evidence_lookback_days=args.evidence_lookback_days)
        result = experiment(service, MarketData.load(symbol=req.symbol), req.model_dump())
    elif args.command == 'predict':
        from backend.app.news.forecasting import predict_saved
        result = predict_saved(service,args.model_id,args.origin)
    else: result = service.records.get(args.kind,args.id)
    print(json.dumps(result, indent=2, allow_nan=False))

if __name__ == '__main__':
    try: main()
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr); sys.exit(1)
