select
    *
from
    {{ dataset }}.request_log
where
    search(body, r'10000001', json_scope=>'JSON_VALUES')
;