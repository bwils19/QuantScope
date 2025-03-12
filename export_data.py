import json
import os
from datetime import datetime
from backend.app import create_app
from backend.models import *
from backend import db


def date_serializer(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


app = create_app()

with app.app_context():
    # Export all tables
    tables = {
        'users': User,
        'portfolios': Portfolio,
        'securities': Security,
        'historical_data': SecurityHistoricalData,
        'stock_cache': StockCache,
        'portfolio_files': PortfolioFiles,
        'historical_data_update_log': HistoricalDataUpdateLog,
        'watchlists': Watchlist,
        'security_metadata': SecurityMetadata,
        'risk_analysis_cache': RiskAnalysisCache,
        'stress_scenarios': StressScenario
    }

    for name, model in tables.items():
        print(f"Exporting {name}...")
        records = model.query.all()
        data = []

        for record in records:
            # Convert to dictionary
            record_dict = {}
            for column in model.__table__.columns:
                record_dict[column.name] = getattr(record, column.name)
            data.append(record_dict)

        # Save to file
        with open(f'{name}_data.json', 'w') as f:
            json.dump(data, f, default=date_serializer)

        print(f"Exported {len(data)} records for {name}")

print("Export complete!")
