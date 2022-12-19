# ダミーデータの作成

以下、GCPコンソールのBigQueryで行う。

データセット`test_search_index`でダミーデータの作成を行う。

## シードデータの作成

### ログのサンプルデータの読み込み

以下のように設定する
1. データセット`test_search_index`の右側からテーブルを作成を選ぶ
1. 設定は以下のようにする
    - テーブルの作成元 : `アップロード`
    - ファイルを選択 : [data/output/配下のlog_combination.jsonl](data/output/log_combination.jsonl)
    - ファイル形式 : `JSONL（改行区切り JSON）`
    - テーブル(名) : `log_sample_base`
    - スキーマ : テキストとして編集をオンにして、以下を入力
        ```
        userid:string,userip:string,request:json,response:json
        ```
1. `テーブルを作成`を押す
1. 以下のSQLによって、ログの種類と順番に関して番号を振ったテーブルを作成する
    ```
    create table test_search_index.log_sample (
        userid string
        , userip string
        , request json
        , response json
        , request_id int64
        , request_number int64
    )
    as
    select
        userid
        , userip
        , request
        , response
        , dense_rank() over (order by to_json_string(request))
        , row_number() over (
            partition by to_json_string(request)
            order by if(json_value(response.status) = 'request', 0, 1)
          )
    from
        test_search_index.log_sample_base
    ;
    ```


### ユーザーリストを作成する

ユーザーIDとIPアドレス、ログ(リクエスト)の種類ごとのログの数を保持するテーブルを作成する(以下のSQLを実行する)。
IPアドレスはログ(リクエスト)ごとにどれかを選ぶようにする

```
create or replace table test_search_index.users (
    userid int64
    , userip array<string>
    , requests array<struct<
        request_id int64
        , request_count int64
      >>
)
as
select
    userid
    , array(
        select (
            select string_agg(format('%d', cast(ceil((1 - rand()) * 254) as int64)), '.')
            from unnest(generate_array(1, 4))
        )
        from unnest(userip)
      )
    , array(
        select as struct
            request_id
            , cast(ceil((1 - rand()) * 40) as int64) as request_count
        from unnest(requests) request_id
      )
from (
    select
        10000000 + userid as userid
        , generate_array(1, cast(ceil((1 - rand()) * 6) as int64)) as userip
        , generate_array(1, (select max(request_id) from test_search_index.log_sample)) as requests
    from
        unnest(generate_array(1, 200000)) userid
)
;
```

以下のSQLで作成されるログデータの行数を確認できる (だいたい1億行ほどできる)
```
select 
    sum(r.request_count) * 2 as log_count
from
    test_search_index.users
    , unnest(requests) r
;

+-----------+
| log_count |
+-----------+
|  98413876 |
+-----------+
```

## ログデータを作成する

上で作ったシードデータからログを作成する (45 ~ 50分くらいかかる)。
以下のSQLを実行すると、10GBほどのテーブルができるため注意

```
create or replace table test_search_index.request_log (
    request_timestamp int64
    , severity string
    , body json
)
;

for record in (select i from unnest(generate_array(0, 19)) i)
do
    insert into 
        test_search_index.request_log (
            request_timestamp
            , severity
            , body
        )
    with users as (
        select
            *
        from
            test_search_index.users u
        where
            userid - 10000000 between 10000 * record.i + 1 and 10000 * (record.i + 1)
    )
    select
        if(status = 'request', request_timestamp, request_timestamp + processing_time) as request_timestamp
        , if(status = 'request', 'INFO', 'NOTICE') as severity
        , to_json((
            select as struct
                format('%d', userid) as userId
                , userip as userIp
                , parse_json(replace(replace(to_json_string(request), r'"id"', format('%d', id)), r'"uuid"', format('"%s"', uuid))) as request
                , if(processing_time is not null, parse_json(replace(to_json_string(response), format('%d', standard_processing_time), format('%d', processing_time))), response) as response
          ))
    from (
        select
            v.userid
            , v.userip
            , v.request_timestamp
            , v.id
            , v.uuid
            , l.request
            , l.response
            , int64(l.response.processingTime) as standard_processing_time
            , cast(ceil((1 - rand()) * int64(l.response.processingTime) * 2) as int64) as processing_time
            , json_value(l.response, '$.status') as status
        from 
            (
                select
                    u.userid as userid
                    , u.userip[offset(cast(floor(rand() * array_length(u.userip)) as int64))] as userip
                    , unix_micros(timestamp "2000-01-01 00:00:00+09") + cast(rand() * 700000000 * 1000000 as int64) as request_timestamp
                    , 10000000 + cast(ceil(rand() * 10000000) as int64) as id
                    , generate_uuid() as uuid
                    , r.request_id
                from
                    users u
                    inner join unnest(u.requests) r
                    inner join unnest(generate_array(1, r.request_count))
            ) v
            inner join test_search_index.log_sample l on v.request_id = l.request_id
    )
    ;
end for
;
```

## ログデータにインデックスを作成する

上で作成したログデータにインデックスを作成する。

比較作業の効率化のため、インデックスは別テーブルを作成の上付与している。
インデックス作成完了までに、30分くらいみておくと良い

```
create or replace table test_search_index.request_log_index
clone test_search_index.request_log
;

create search index performance_test_index
on test_search_index.request_log_index(body)
options (analyzer = 'LOG_ANALYZER')
;
```

インデックスの作成状況は以下のSQLで確認できる。
`coverage_percentage`が100になっていれば作成が完了している。
なお、このSQLで結果がない場合は、インデックスの作成が開始していない(おそらくテーブルのデータ量不足が原因)。
```
select
    table_name, index_name, index_status, coverage_percentage, total_logical_bytes, total_storage_bytes
from
    test_search_index.INFORMATION_SCHEMA.SEARCH_INDEXES
where
    index_status = 'ACTIVE'
;
```

# その他

## script内のスクリプトの使い方

### 準備(Dockerコンテナの起動)

Cloud Shellで実行する場合は、以下の1. ~ 3.は実行しないで問題ない。

1. 以下の権限(ロール)を付与したサービスアカウントを作成して、鍵(JSON)を作成する。
    - `BigQuery閲覧者`
    - `BigQuery ジョブユーザー`
    - `BigQuery リソース閲覧者` (`INFORMATION_SCHEMA`へのクエリに必要)
1. 鍵ファイルの絶対パスを変数指定しておく。
    ```
    key_file=[/path/to/key_file.json]
    ```
1. Dockerコンテナの起動
    ```
    docker run -it --rm -w /home \
        -e GOOGLE_APPLICATION_CREDENTIALS=/home/.config/gcloud/application_default_credentials.json \
        --mount type=bind,source="$(pwd)"/data,target=/home/data \
        --mount type=bind,source="$(pwd)"/data_test,target=/home/data_test \
        --mount type=bind,source="$(pwd)"/requirements.txt,target=/home/requirements.txt \
        --mount type=bind,source="$(pwd)"/script,target=/home/script \
        --mount type=bind,source="$(pwd)"/sql,target=/home/sql \
        --mount type=bind,source=$key_file,target=/home/.config/gcloud/application_default_credentials.json \
        python3.11:slim /bin/bash
    ```
1. 必要なパッケージのインストール
    ```
    pip install -r requirements.txt
    ```

### スクリプトの実行

#### パフォーマンステスト

※ 大量のダミーデータを作成していると月の無料枠を超えて課金される可能性があるため注意

[sql/time](sql/time/)配下の01 ~ 03のSQLを5回ずつ実行し、実行時間とテーブルスキャン量を記録する

- テストの実施
    ```
    python3 script/time_query.py -l [dataset_location] -d test_search_index
    ```
- `time_result.tsv`に実行結果が記録される
    ```
    cat time_result.tsv

    query_id        job_id  creation_time   query   total_bytes_processed   total_bytes_billed      total_elapsed_ms        total_slot_ms
    01      aaaaaaa    2000-01-01 00:00:00.000000+00:00        "select
    ...
    ```

#### ログのサンプルデータの作成

`YAML`ファイル内の配列の全ての組み合わせを展開し、`JSON`または`JSONL`ファイルを作成する

[data/input](data/input)配下の`YAML`ファイル名を指定して、[data/output](data/output)配下に同名の`JSONL`ファイルが作成される

`-t`オプションを使用することで、[data_test](data_test)配下のファイルを指定できる(生成例もこのファイルから確認できる)

- スクリプトの実行
    ```
    python3 script/generate_log.py log_combination.yaml
    ```
- `data/output/log_combination.jsonl`が生成される
