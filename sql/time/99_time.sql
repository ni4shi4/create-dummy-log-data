select
    job_id
    , creation_time
    , query
    , total_bytes_processed
    , total_bytes_billed
    , timestamp_diff(end_time, start_time, millisecond) as total_elapsed_ms
    , total_slot_ms
from
    `region-{{ location }}`.INFORMATION_SCHEMA.JOBS
where 
    job_id in (select job_id from unnest(@job_ids) job_id)
order by
    creation_time desc
;