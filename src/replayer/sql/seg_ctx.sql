with MsgEid as (
    select eid from segments
    where $cond
    limit 1
)
select time, uid, type, text, nickname, data from segments
where eid in (
    select eid from (
        select distinct eid from segments 
        where eid < (select eid from MsgEid) and gid=$gid
        order by eid desc
        limit $lof
    )
    union all
    select eid from (
        select distinct eid from segments
        where eid >= (select eid from MsgEid) and gid=$gid
        order by eid
        limit $rof
    )
)
order by eid, idx