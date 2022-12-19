#!/usr/bin/env python3

import os
import argparse
from pathlib import Path
from jinja2 import Template

import pandas as pd
from google.cloud import bigquery

def load_sql_file(
    sql_file_path: Path
) -> str:
    return sql_file_path.read_text()

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-l", "--location", type=str
        , help="dataset location", required=True
    )
    parser.add_argument(
        "-d", "--dataset", type=str
        , help="dataset name", required=True
    )

    return parser.parse_args()

def parse_dir() -> Path:
    script_dir = Path(os.path.dirname(__file__))
    
    return script_dir / "../sql/time"

def run_query(
    bigquery_client: bigquery.Client, 
    job_config: bigquery.QueryJobConfig,
    dataset: str,
    query_id: str, 
    sql_path: Path 
) -> pd.DataFrame:
    template = Template(load_sql_file(sql_path))
    replaced_query = template.render(dataset=dataset)
    job_df = pd.DataFrame(columns=["query_id", "job_id"])
    # 5回計測する
    for _ in range(5):
        query_job = bigquery_client.query(replaced_query, job_config=job_config)
        query_job.result(max_results=1)
        job_df_tmp = pd.DataFrame({
            "query_id": [query_id], 
            "job_id": [query_job.job_id]
        })
        job_df = pd.concat([job_df, job_df_tmp])
    
    return job_df

def execute_query(
    args: argparse.Namespace, sql_dir: Path
) -> pd.DataFrame:
    bigquery_client = bigquery.Client(location=args.location)
    job_config = bigquery.QueryJobConfig(use_query_cache=False)

    job_df = pd.DataFrame(columns=["query_id", "job_id"])
    queries = {
        "01": "01_simple_query.sql",
        "02": "02_search_query.sql",
        "03": "03_search_index_query.sql"
    }
    queries = { 
        query_id: sql_dir / query_file_name
        for query_id, query_file_name in queries.items()
    }
    print("[Query execution] start")

    for query_id, sql_path in queries.items():
        print(f"[Query execution] [Query : {query_id}] start")
        job_df_tmp = run_query(bigquery_client, job_config, args.dataset, query_id, sql_path)
        job_df = pd.concat([job_df, job_df_tmp])
        print(f"[Query execution] [Query : {query_id}] end")
    print("[Query execution] end")

    return job_df.reset_index(drop=True)

def time_query(
    args: argparse.Namespace, sql_dir: Path, job_df: pd.DataFrame
) -> pd.DataFrame:
    bigquery_client = bigquery.Client(location=args.location)
    
    print("[Get job config] start")
    template = Template(load_sql_file(sql_dir / "99_time.sql"))
    replaced_query = template.render(location=args.location)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("job_ids", "STRING", list(job_df["job_id"].to_numpy()))
        ]
    )
    query_job = bigquery_client.query(replaced_query, job_config=job_config)
    result = query_job.to_arrow().to_pandas()
    print("[Get job config] end")

    print("[Save job config] start")
    result = pd.merge(job_df, result, on="job_id", how="left")
    result.to_csv("time_result.tsv", index=False, sep="\t")
    print("[Save job config] end")

if __name__ == "__main__":
    args = parse_args()
    sql_dir = parse_dir()
    job_df = execute_query(args, sql_dir)
    time_query(args, sql_dir, job_df)
