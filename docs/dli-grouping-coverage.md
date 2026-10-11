# DLI 分组规则审查与覆盖

此次只审查与聚合/分组有关的 Spark SQL 语法，不把 Flink SQL、HetuEngine 或 DWS 语法当成 DLI Spark 依据，也不宣称全量支持所有 DLI 语句。

## 文档依据

- 华为云 DLI：[ROLLUP](https://support.huaweicloud.com/intl/en-us/sqlref-spark-dli/dli_08_0163.html)：层次小计和总计，维度可在汇总层变成 NULL；文档展示 WITH 写法。
- 华为云 DLI：[GROUPING SETS](https://support.huaweicloud.com/sqlref-spark-dli/dli_08_0164.html)：集合可包含字段组合、单列及空集合。旧版文档主要展示前置 GROUP BY 形式。
- 华为云 DLI：[按表达式分组](https://support.huaweicloud.com/sqlref-spark-dli/dli_08_0161.html)：分组表达式允许标量函数等结构，需要按完整表达式核对。
- 华为云 DLI：[HAVING](https://support.huaweicloud.com/sqlref-spark-dli/dli_08_0162.html)：聚合后的过滤，与 WHERE 的行过滤区分。
- 华为云 DLI：[常用配置](https://support.huaweicloud.com/sqlref-spark-dli/dli_08_0266.html)：CUBE / ROLLUP 与 count(distinct) 相关执行计划可能受配置影响。静态检测不推断实际计划或修改配置。
- Spark 上游补充：[分组语义](https://spark.apache.org/docs/3.5.7/sql-ref-syntax-qry-select-groupby.html) 与 [grouping_id 参数](https://spark.apache.org/docs/3.5.7/api/python/reference/pyspark.sql/api/pyspark.sql.functions.grouping_id.html)。用于解释函数式、混合、嵌套及函数参数语义；具体 DLI 引擎/区域版本能否执行仍需验证。

文档有不同版本和区域。某些旧页对“分组表达式可含聚合函数”的文字表述较宽泛；本工具对明确聚合分组项仍提醒核对，以实际 DLI 分析器为准，不将文档中的宽泛措辞当成所有函数都合法的证明。

## 实现方式

分组容器与标量表达式分开处理。只展开 rollup/cube/grouping sets/tuple/括号容器的**维度全集**，保留 IF、RLIKE 等标量表达式原有结构。非聚合输出必须被这个维度全集覆盖。某维度缺席于某个小计集合不构成漏分组，因为汇总行可以输出 NULL；没有声明过的输出字段才需要优先提示。

不枚举 CUBE 的全部集合，避免本地检查因指数数量的组合变慢。前置 GROUP BY + 显式 GROUPING SETS 中未进入任何集合的维度，以潜在固定 NULL 的风险提醒，具体行为须核对 DLI 版本。

## 覆盖矩阵

| 场景 | 行为 |
| --- | --- |
| 普通字段/表达式、别名和序号分组 | 继承普通一致性检查 |
| rollup(expr...) / expr... with rollup | 核对全部声明维度与非聚合输出 |
| cube(expr...) / expr... with cube | 同上，覆盖 count(distinct) 输入 |
| grouping sets((a,b),(a),(b),()) | 按全集检查，空集合不会误报合法维度 |
| GROUP BY a,b GROUPING SETS(...) | 支持前置项，并提示维度不进入任何显式集合的风险 |
| tuple、嵌套、混合多维分组 | 保留表达式边界，收集维度全集 |
| IF/RLIKE 类型表达式 + 原因 + count | 只按类型 rollup 时，明确指出原因未分组 |
| grouping(expr) | 核对多维上下文和表达式对应关系 |
| grouping_id() / grouping_id(expr...) | 核对上下文、成员、参数完整性和顺序；版本相关差异提示验证 |
| HAVING / ORDER BY | 核对未分组字段，支持唯一输出别名及聚合表达式 |
| WHERE 中直接聚合 | 优先提示移至合适的 HAVING / 外层查询 |
| 独立或嵌套子查询 | 各自作用域分别判断，不串用分组项 |
| *、多表裸字段、歧义别名 | 提示需要表结构或配置验证，不扩展不存在的 schema |
| GROUP BY ALL | 继续提示 DLI 引擎版本核对，不假定全面兼容 |

## 验证边界

所有测试仅静态解析合成 SQL；报告中原样的业务 SQL 没有提交到 GitHub。对照用户报告的等价结构制作了回归用例：错误版本原因字段未分组会置顶，补足合法维度后不再报该错误。合法小计/总计、空集合、混合和嵌套写法也纳入回归。

没有连接真实 DLI，也没有验证字段存在性/类型、UDAF 签名、队列版本、别名/序号开关、执行计划和结果。复杂相关子查询及任意代数等价表达式不保证完整判定；静态通过不代表一定可在 DLI 执行。
