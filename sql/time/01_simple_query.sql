select
    *
from
    {{ dataset }}.request_log
where
    json_value(body, '$.userId') = '10000001'
;