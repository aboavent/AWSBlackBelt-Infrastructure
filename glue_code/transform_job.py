import sys
from datetime import datetime, timedelta

import pandas as pd
from awsglue.utils import getResolvedOptions
import awswrangler


def add_timestamp(splitted_data: pd.DataFrame) -> pd.DataFrame:
    """ Adds simulated timestamp the the ingested data to replicate 
        real life scenario
        :argument: splitted_data - Pandas Dataframe with data of 24 cycle split with all units
        :return: timestamp_data - Pandas Dataframe with timestamps for 24 cycle for all units
    """
    current_time = datetime.now()
    time_list = []
    # Get number of rows for one unit
    unit_length = len(splitted_data[splitted_data['unit']==1])
    # Iterate over the length of one unit
    for i in range(unit_length):
        # Calculate new time based on difference of current row
        new_time = current_time - timedelta(hours=i)
        # Append the new time as string in list
        time_list.append(new_time.strftime('%Y-%m-%d %H-%M-%S'))
    # Reverse the time list so that current time is last in unit
    time_list.reverse()
    timestamp_data_list = []
    # Iterate over all units
    for unit in splitted_data['unit'].unique():
        # Get rows only for the specified unit
        unit_splitted = splitted_data[splitted_data['unit']==unit]
        # Add the reversed timestamps as additional column
        unit_splitted.loc[:, 'timestamp'] = time_list
        # Append new dataframe for specified unit
        timestamp_data_list.append(unit_splitted)
    # Concatenate all dataframes of specified units into one dataframe
    timestamp_data = pd.concat(timestamp_data_list)
    return timestamp_data

def create_target(raw_data: pd.DataFrame) -> pd.DataFrame:
    """ Creates the RUL target variable based on max cycles from the dataset 
        :argument: raw_data - Pandas DataFrame containing training data
        :return: dataset - Pandas DataFrame containing training data and target variable
    """
    data = raw_data.copy()
    # Group the data by unit column and calculate the max cycle
    grouped = data.groupby('unit')
    max_cycle = grouped['cycle'].max()
    # Merge the max cycle back to the data
    data = data.merge(max_cycle.to_frame(name='max_cycle'), left_on='unit', right_index=True)
    # Calculate difference between max cycle and current cycle, create RUL
    data['rul'] = data['max_cycle'] - data['cycle']
    # Drop the max cycle column
    data.drop('max_cycle', axis=1, inplace=True)
    return data


if __name__ == '__main__':
    # Get the Arguments
    args = getResolvedOptions(sys.argv,
                            ['JOB_NAME',
                            'database_name',
                            'file_key',
                            'ingest_type',
                            'file_name',
                            'bucket'])

    # Define the path to the raw parquet file
    # file_key = args['file_key'].replace('/csv', '/parquet')
    file_key = args['file_key']
    ingest_type = args['ingest_type']
    filename = args['file_name']

    # Get the raw parquet data
    raw_data = awswrangler.s3.read_parquet(path=[f"s3://{args['bucket']}/{file_key}"])

    # Define the data schema for Athena table
    data_schema = {"unit": "int", "cycle": "int", "altitude": "double", "mach": "double", "tra": "double"}
    for i in range(1, 22):
        data_schema[f'sensor_{i}'] = "double"
    
    if ingest_type == 'partitioned':
        curated_data = add_timestamp(raw_data)
        data_schema['timestamp'] = "timestamp"
    else:
        if 'test' in filename:
            table = f"mlops-curated-test-data-{ingest_type}"
        else:
            curated_data = create_target(raw_data)
            table = f"mlops-curated-data-{ingest_type}"
            data_schema['rul'] = 'int'

    # Save transformed data to parquet format
    path = f"s3://{args['bucket']}/curated/{ingest_type}/parquet/{filename.replace('.csv', '.parquet')}"
    awswrangler.s3.to_parquet(curated_data, path=path, dataset=True, mode='append', 
                            database=args['database_name'], table=table, partition_cols=['unit'], dtype=data_schema)
