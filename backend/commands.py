import click
from flask.cli import with_appcontext
from .services.historical_data_service import HistoricalDataService


@click.command('load-historical-data')
@with_appcontext
def load_historical_data():
    """Command to perform initial historical data load"""
    click.echo('Starting initial historical data load...')
    service = HistoricalDataService()
    service.update_historical_data()
    click.echo('Historical data load complete')


