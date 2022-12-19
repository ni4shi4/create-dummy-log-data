select
    search(
        json '''{"domain": "firefish.jp", "company_info": "firefish有限会社"}'''
        , r'jp', json_scope=>'JSON_VALUES'
    ) as result1
    , search(
        json '''{"domain": "firefish.jp", "company_info": "firefish有限会社"}'''
        , r'fish', json_scope=>'JSON_VALUES'
    ) as result2
    , search(
        json '''{"domain": "firefish.jp"
        , "company_info": {"zipcode": "999-1111", "company_name": "firefish有限会社"}}'''
        , r'999', json_scope=>'JSON_VALUES'
    ) as result3
    , search(
        json '''{"domain": "firefish.jp"
        , "affiliated_company": ["fireinsect株式会社", "firewhale Co., Ltd."]}'''
        , r'firewhale', json_scope=>'JSON_VALUES'
    ) as result4
    , search(
        json '''{"domain": "firefish.jp", "company_name": "firefish有限会社"}'''
        , r'company_name', json_scope=>'JSON_KEYS'
    ) as result5
    , search(
        json '''{"domain": "firefish.jp", 
        "company_info": {"zipcode": "999-1111", "company_name": "firefish有限会社"}}'''
        , r'zipcode', json_scope=>'JSON_KEYS'
    ) as result6
    , search(
        (json '''{"domain": "firefish.jp"
        , "company_info": {"zipcode": "999-1111", "company_name": "firefish有限会社"}}''').company_info
        , r'zipcode', json_scope=>'JSON_KEYS'
    ) as result7
    , search(
        json '''{"domain": "firefish.jp"
        , "company_info": {"zipcode": "999-1111", "company_name": "firefish有限会社"}}'''
        , r'zipcode', json_scope=>'JSON_KEYS_AND_VALUES'
    ) as result8
    , search(
        json '''{"domain": "firefish.jp"
        , "company_info": {"zipcode": "999-1111", "company_name": "firefish有限会社"}}'''
        , r'zipcode', json_scope=>'JSON_VALUES'
    ) as result9
    , search(
        json '''{"domain": "firefish.jp"
        , "company_info": {"zipcode": "999-1111", "company_name": "firefish有限会社"}}'''
        , r'`company_info.zipcode`', json_scope=>'JSON_KEYS'
    ) as result10
    , search(
        json '''{"int64": 10, "float64": 10.0}'''
        , r'10', json_scope=>'JSON_KEYS_AND_VALUES'
    ) as result11
;