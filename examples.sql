-- 示例 1：含风险，用于验证检查器
select
    a.region
    ,b.shipper_id
    ,sum(a.amount) / sum(a.cnt) as `平均金额`
from orders a
left join shippers b on a.shipper_id = a.shipper_id
where a.dt between '${month_1}' and '${dt}'
group by
    a.region;

-- 示例 2：常见 DLI JSON 提取与模板
select
    get_json_object(payload, '$.sceneParams.unloadingVehicleImage') as `卸货车辆照片`
    ,get_json_object(payload, '$.common.orderItemSn') as `运单号`
from synthetic_events
where dt = '${dt}';
