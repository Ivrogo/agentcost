<!-- agentcost-ci -->
# agentcost

**Verdict:** worse
**Gate:** regression
**Mode:** paired (5 pairs)
**Metric:** cost
**Difference (A - B):** $4
**95% CI:** [$4, $4]
**Includes 0:** no
**Relative change:** 100%
**Relative 95% CI:** [100%, 100%]
**Threshold:** 5% on the lower bound of the relative 95% CI
**Compared value:** 100%
**Fail if worse:** yes

A costs more per paired task than B; the bootstrap 95% interval of the mean difference does not include 0.

A is worse than B on cost: the 95% CI of the mean difference is entirely above 0. The lower bound of the relative 95% CI is 100%, which exceeds the 5% threshold.

| Metric | A | B |
| --- | ---: | ---: |
| Tasks | 5 | 5 |
| Successful tasks | 5 | 5 |
| Cost per solved task | $8 | $4 |
| Total cost | $40 | $20 |
